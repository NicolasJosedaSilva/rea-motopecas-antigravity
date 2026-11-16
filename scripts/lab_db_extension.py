"""Laboratório de evolução do SQLite da Rota 2 — SOMENTE bancos lab_*.db.

Execute da raiz do repositório (Windows: .\\.venv\\Scripts\\python.exe ...):
  python scripts/lab_db_extension.py init     --db data/lab_rota2.db
  python scripts/lab_db_extension.py backup   --db data/lab_rota2.db --label baseline
  python scripts/lab_db_extension.py restore  --db data/lab_rota2.db --label baseline
  python scripts/lab_db_extension.py migrate  --db data/lab_rota2.db
  python scripts/lab_db_extension.py adjust   --db data/lab_rota2.db --sku R2-FR-001 --quantity 25 --reason inventario-aula
  python scripts/lab_db_extension.py verify   --db data/lab_rota2.db
  python scripts/lab_db_extension.py backup   --db data/lab_rota2.db --label pos_migracao
  python scripts/lab_db_extension.py restore  --db data/lab_rota2.db --label pos_migracao
  python scripts/lab_db_extension.py rollback --db data/lab_rota2.db --yes

A lógica de migração, ajuste e conciliação vem de app/ (fonte única: migrations/*.sql,
app/migrations.py, app/ledger.py). Este script só orquestra o ensaio e NÃO toca em
data/motopecas.db. Códigos de saída de verify: 0 = PASS, 2 = falha, 3 = NÃO VERIFICADO.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

# Permite importar app/ quando executado como scripts/lab_db_extension.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LABEL_RE = re.compile(r"^[a-z0-9_]{1,30}$")


def safe_path(value: str) -> Path:
    p = Path(value).expanduser().resolve()
    if not p.name.lower().startswith("lab_") or p.suffix.lower() not in (".db", ".sqlite", ".sqlite3"):
        raise SystemExit("SEGURANÇA: use banco lab_*.db, separado de data/motopecas.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def conn_for(p: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(p), timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    return db


def sha256_of(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sibling(p: Path, label: str, suffix_extra: str = "") -> Path:
    if not LABEL_RE.match(label):
        raise SystemExit("--label inválido: use letras minúsculas, dígitos e _ (máx. 30)")
    return p.with_name(f"{p.stem}_{label}{suffix_extra}{p.suffix}")


def cmd_init(p: Path) -> int:
    """Baseline: banco como na versão original (4 tabelas, 12 produtos, SEM ledger)."""
    os.environ["MOTO_DB_PATH"] = str(p)
    from app.db import initialize
    initialize(migrate=False)
    with closing(conn_for(p)) as db:
        print("Base pronta:", db.execute("SELECT COUNT(*) FROM products").fetchone()[0], "produtos (baseline, sem ledger)")
    return 0


def cmd_backup(p: Path, label: str) -> int:
    if not p.exists():
        raise SystemExit("Banco inexistente; execute init primeiro")
    target = sibling(p, label)
    if target.exists():
        raise SystemExit(f"Backup existente ({target.name}): use outro --label ou renomeie-o")
    with closing(conn_for(p)) as source, closing(sqlite3.connect(str(target))) as dest:
        source.backup(dest)  # Online Backup API (não copia o arquivo aberto)
    digest = sha256_of(target)
    meta = {
        "source": str(p), "backup": str(target), "label": label, "sha256": digest,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "sqlite_version": sqlite3.sqlite_version,
    }
    (target.parent / (target.name + ".sha256")).write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    (target.parent / (target.name + ".metadata.json")).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Backup completo:", target.name, "| sha256:", digest)
    return 0


def cmd_restore(p: Path, label: str) -> int:
    """Restaura em NOVO arquivo lab_*_restored.db, sem sobrescrever a base, e valida."""
    source = sibling(p, label)
    target = sibling(p, label, "_restored")
    if not source.exists():
        raise SystemExit("Backup ausente; execute backup primeiro")
    if target.exists():
        raise SystemExit(f"Restauração já existe ({target.name}); não sobrescrever")
    hash_note = "hash NÃO VERIFICADO (sem arquivo .sha256)"
    hash_file = source.parent / (source.name + ".sha256")
    if hash_file.exists():
        expected = hash_file.read_text(encoding="utf-8").split()[0]
        if sha256_of(source) != expected:
            raise SystemExit("FALHA: SHA-256 do backup não confere com o registrado")
        hash_note = "sha256 confere"
    from app.ledger import check
    with closing(sqlite3.connect(str(source))) as src, closing(sqlite3.connect(str(target))) as dest:
        src.backup(dest)
    with closing(conn_for(target)) as db:
        report = check(db)
        products = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    problems = report["integrity_check"] != "ok" or report["foreign_key_violations"] or report["discrepancies"]
    if problems:
        raise SystemExit(f"FALHA ao validar restauração: {report}")
    ledger_note = "ledger conciliado" if report["ledger"] else "sem ledger (baseline)"
    print(f"RESTORE PASS: {target.name} | produtos: {products} | integrity=ok | FK violadas: 0 | {ledger_note} | {hash_note}")
    return 0


def cmd_migrate(p: Path) -> int:
    if not p.exists():
        raise SystemExit("Banco inexistente; execute init primeiro")
    from app import migrations
    with closing(conn_for(p)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='products'").fetchone():
            raise SystemExit("Baseline ausente; execute init primeiro")
        done = migrations.apply_pending(db)
    print("Migrações aplicadas: " + ", ".join(done) if done else "Migração já aplicada; sem alterações")
    print("ATENÇÃO: não rode pedidos pela API num banco que não use o código com ledger integrado.")
    return 0


def cmd_rollback(p: Path, yes: bool) -> int:
    if not yes:
        raise SystemExit("Reversão apaga o histórico de movimentos; confirme com --yes (faça backup antes)")
    from app import migrations
    with closing(conn_for(p)) as db:
        reverted = migrations.rollback_last(db)
    print(f"Migração revertida: {reverted}" if reverted else "Nada a reverter")
    return 0


def cmd_adjust(p: Path, sku: str, quantity: int, reason: str) -> int:
    from app import ledger
    with closing(conn_for(p)) as db:
        try:
            before, after, delta = ledger.adjust_stock(db, sku, quantity, reason)
        except (ValueError, LookupError, ledger.LedgerUnavailable) as exc:
            raise SystemExit(f"ERRO: {exc}")
    print("SKU:", sku, "de:", before, "para:", after, "delta:", delta)
    return 0


def cmd_verify(p: Path) -> int:
    from app.ledger import check
    with closing(conn_for(p)) as db:
        report = check(db)
    print("SQLite:", report["sqlite_version"], "integrity:", report["integrity_check"],
          "FK violations:", report["foreign_key_violations"],
          "ledger discrepancies:", len(report["discrepancies"]) if report["ledger"] else "n/a")
    for row in report["discrepancies"][:20]:
        print(row)
    if report["integrity_check"] != "ok" or report["foreign_key_violations"] or report["discrepancies"]:
        return 2
    if not report["ledger"]:
        print("NÃO VERIFICADO: migração 001 não aplicada; conciliação não executada.")
        return 3
    print("PASS: conciliação e integridade. Este PASS não prova integração com API/CLI.")
    return 0


def main() -> int:
    a = argparse.ArgumentParser(description="Laboratório de evolução SQLite — só banco lab_*.db")
    a.add_argument("action", choices=["init", "backup", "restore", "migrate", "rollback", "adjust", "verify"])
    a.add_argument("--db", required=True)
    a.add_argument("--label", default="backup", help="sufixo do backup/restauração (padrão: backup)")
    a.add_argument("--sku")
    a.add_argument("--quantity", type=int)
    a.add_argument("--reason", default="")
    a.add_argument("--yes", action="store_true")
    z = a.parse_args()
    p = safe_path(z.db)
    if z.action == "init":
        return cmd_init(p)
    if z.action == "backup":
        return cmd_backup(p, z.label)
    if z.action == "restore":
        return cmd_restore(p, z.label)
    if z.action == "migrate":
        return cmd_migrate(p)
    if z.action == "rollback":
        return cmd_rollback(p, z.yes)
    if z.action == "verify":
        return cmd_verify(p)
    if z.sku is None or z.quantity is None:
        a.error("--sku e --quantity são obrigatórios para adjust")
    return cmd_adjust(p, z.sku, z.quantity, z.reason)


if __name__ == "__main__":
    sys.exit(main())
