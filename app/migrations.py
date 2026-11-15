"""Executor mínimo de migrações SQL versionadas (pasta migrations/).

Cada versão tem um arquivo NNN_nome.sql (subida) e, opcionalmente,
NNN_nome.down.sql (reversão). Cada migração roda em UMA transação
(BEGIN IMMEDIATE ... COMMIT): se qualquer instrução falhar, nada é aplicado.
A conexão deve estar em modo autocommit (isolation_level=None), como em db.connect().
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_UP_FILE = re.compile(r"^(\d{3}_[a-z0-9_]+)\.sql$")


class MigrationError(RuntimeError):
    """Falha ao aplicar ou reverter uma migração (a transação foi desfeita)."""


class MigrationPending(RuntimeError):
    """Existem migrações não aplicadas num banco que já contém dados."""


def available(directory: Path | None = None) -> list[str]:
    """Versões encontradas na pasta, em ordem."""
    directory = directory or MIGRATIONS_DIR
    found = []
    for item in sorted(directory.glob("*.sql")):
        match = _UP_FILE.match(item.name)
        if match:
            found.append(match.group(1))
    return found


def _table_exists(db: sqlite3.Connection, name: str) -> bool:
    row = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def applied(db: sqlite3.Connection) -> list[str]:
    """Versões já aplicadas (somente leitura: não cria tabela alguma)."""
    if not _table_exists(db, "schema_migrations"):
        return []
    return [r[0] for r in db.execute("SELECT version FROM schema_migrations ORDER BY version")]


def pending(db: sqlite3.Connection, directory: Path | None = None) -> list[str]:
    done = set(applied(db))
    return [v for v in available(directory) if v not in done]


def require_up_to_date(db: sqlite3.Connection, directory: Path | None = None) -> None:
    """Falha fechado se houver migração pendente (não altera o banco)."""
    todo = pending(db, directory)
    if todo:
        raise MigrationPending(
            "Migração pendente: " + ", ".join(todo)
            + ". Faça backup e execute: python -m app.manage migrate"
        )


def _has_code(text: str) -> bool:
    return any(line.strip() and not line.strip().startswith("--") for line in text.splitlines())


def _statements(sql: str):
    """Divide o script em instruções completas (inclui triggers com BEGIN...END)."""
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if _has_code(statement):
                yield statement
    if _has_code(buffer):
        raise MigrationError("Instrução incompleta no final do arquivo de migração")


def _read(directory: Path | None, filename: str) -> str:
    path = (directory or MIGRATIONS_DIR) / filename
    if not path.is_file():
        raise MigrationError(f"Arquivo de migração ausente: {path.name}")
    return path.read_text(encoding="utf-8")


def _ensure_table(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )


def _rollback_quietly(db: sqlite3.Connection) -> None:
    if db.in_transaction:
        db.execute("ROLLBACK")


def _apply_one(db: sqlite3.Connection, version: str, directory: Path | None) -> bool:
    sql = _read(directory, f"{version}.sql")
    db.execute("BEGIN IMMEDIATE")
    try:
        _ensure_table(db)
        if db.execute("SELECT 1 FROM schema_migrations WHERE version=?", (version,)).fetchone():
            db.execute("COMMIT")  # outro processo aplicou antes de nós
            return False
        for statement in _statements(sql):
            db.execute(statement)
        db.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
        db.execute("COMMIT")
        return True
    except BaseException:
        _rollback_quietly(db)
        raise


def apply_pending(db: sqlite3.Connection, directory: Path | None = None) -> list[str]:
    """Aplica, em ordem, as migrações pendentes. Retorna as versões aplicadas agora."""
    done_now = []
    for version in pending(db, directory):
        if _apply_one(db, version, directory):
            done_now.append(version)
    return done_now


def rollback_last(db: sqlite3.Connection, directory: Path | None = None) -> str | None:
    """Reverte a última migração aplicada (se houver). Retorna a versão revertida."""
    db.execute("BEGIN IMMEDIATE")
    try:
        _ensure_table(db)
        row = db.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()
        if row is None:
            db.execute("COMMIT")
            return None
        version = row[0]
        for statement in _statements(_read(directory, f"{version}.down.sql")):
            db.execute(statement)
        db.execute("DELETE FROM schema_migrations WHERE version=?", (version,))
        db.execute("COMMIT")
        return version
    except BaseException:
        _rollback_quietly(db)
        raise
