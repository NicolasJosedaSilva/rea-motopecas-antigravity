"""Exercício 2 — laboratório isolado (scripts/lab_db_extension.py): backup, restore, migração, verify."""
import sqlite3

from ledger_support import run_lab


def lab(tmp_path, *args):
    return run_lab(*args, "--db", str(tmp_path / "lab_rota2.db"))


def test_lab_refuses_non_lab_database(tmp_path):
    r = run_lab("init", "--db", str(tmp_path / "producao.db"))
    assert r.returncode != 0
    assert "SEGURANÇA" in r.stderr
    assert not (tmp_path / "producao.db").exists()


def test_lab_full_sequence_with_two_backup_restore_cycles(tmp_path):
    steps = [
        (("init",), 0, "Base pronta: 12"),
        (("backup", "--label", "baseline"), 0, "sha256"),
        (("restore", "--label", "baseline"), 0, "RESTORE PASS"),
        (("verify",), 3, "NÃO VERIFICADO"),                    # baseline: sem ledger, sem falso PASS
        (("migrate",), 0, "001_inventory_ledger"),
        (("migrate",), 0, "já aplicada"),                      # idempotente
        (("verify",), 0, "PASS"),
        (("adjust", "--sku", "R2-FR-001", "--quantity", "25", "--reason", "inventario-aula"), 0, "delta: 5"),
        (("verify",), 0, "PASS"),
        (("backup", "--label", "pos_migracao"), 0, "sha256"),
        (("restore", "--label", "pos_migracao"), 0, "ledger conciliado"),
    ]
    for args, expected_rc, expected_text in steps:
        r = lab(tmp_path, *args)
        assert r.returncode == expected_rc, (args, r.stdout, r.stderr)
        assert expected_text in r.stdout, (args, r.stdout)
    for name in ("lab_rota2_baseline.db", "lab_rota2_baseline_restored.db",
                 "lab_rota2_pos_migracao.db", "lab_rota2_pos_migracao_restored.db"):
        assert (tmp_path / name).exists(), name


def test_lab_verify_detects_divergence(tmp_path):
    assert lab(tmp_path, "init").returncode == 0
    assert lab(tmp_path, "migrate").returncode == 0
    with sqlite3.connect(tmp_path / "lab_rota2.db") as db:
        db.execute("UPDATE products SET stock = stock - 1 WHERE sku = 'R2-FR-001'")
    r = lab(tmp_path, "verify")
    assert r.returncode == 2
    assert "R2-FR-001" in r.stdout


def test_lab_backup_refuses_overwrite_and_records_hash(tmp_path):
    assert lab(tmp_path, "init").returncode == 0
    assert lab(tmp_path, "backup").returncode == 0
    assert (tmp_path / "lab_rota2_backup.db.sha256").read_text(encoding="utf-8").split()[0]
    assert (tmp_path / "lab_rota2_backup.db.metadata.json").exists()
    again = lab(tmp_path, "backup")
    assert again.returncode != 0 and "existente" in again.stderr


def test_lab_restore_detects_tampered_backup(tmp_path):
    assert lab(tmp_path, "init").returncode == 0
    assert lab(tmp_path, "backup").returncode == 0
    with open(tmp_path / "lab_rota2_backup.db", "ab") as f:
        f.write(b"adulterado")
    r = lab(tmp_path, "restore")
    assert r.returncode != 0
    assert "SHA-256" in r.stderr
    assert not (tmp_path / "lab_rota2_backup_restored.db").exists()


def test_lab_rollback_requires_confirmation(tmp_path):
    assert lab(tmp_path, "init").returncode == 0
    assert lab(tmp_path, "migrate").returncode == 0
    assert lab(tmp_path, "rollback").returncode != 0
    assert lab(tmp_path, "rollback", "--yes").returncode == 0
    assert lab(tmp_path, "verify").returncode == 3
