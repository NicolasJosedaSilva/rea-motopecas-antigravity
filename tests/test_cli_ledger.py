"""Exercício 2 — G-DB5 (caminho CLI): ajustes de estoque registram movimentos; migrate/rollback/reconcile."""
from ledger_support import (  # noqa: F401  (fixtures e utilitários)
    ledger_db, legacy_db, oracle_discrepancies, q, run_cli,
)

STOCK_R2_FR_001 = "SELECT stock FROM products WHERE sku='R2-FR-001'"
ADJUSTMENTS = "SELECT COUNT(*) FROM inventory_movements WHERE movement_type='ADJUSTMENT'"


def test_cli_stock_registers_adjustment_movement(ledger_db):
    r = run_cli("stock", "R2-FR-001", "37", "--reason", "inventario-aula")
    assert r.returncode == 0, r.stderr
    assert "estoque atualizado para 37" in r.stdout  # saída original preservada
    assert q("SELECT movement_type, delta_qty, reason, order_id FROM inventory_movements "
             "WHERE movement_type='ADJUSTMENT'") == [("ADJUSTMENT", 17, "inventario-aula", None)]
    assert q(STOCK_R2_FR_001) == [(37,)]
    assert oracle_discrepancies() == []


def test_cli_stock_without_reason_keeps_old_usage(ledger_db):
    """Regressão: 'stock SKU QTD' (sem --reason) continua funcionando."""
    r = run_cli("stock", "R2-FR-001", "37")
    assert r.returncode == 0, r.stderr
    assert q("SELECT reason FROM inventory_movements WHERE movement_type='ADJUSTMENT'") == \
        [("ajuste administrativo via CLI",)]


def test_cli_stock_same_quantity_creates_no_movement(ledger_db):
    assert run_cli("stock", "R2-FR-001", "20").returncode == 0
    assert q(ADJUSTMENTS) == [(0,)]


def test_cli_rejects_invalid_input_without_writing(ledger_db):
    for args in (("R2-FR-001", "-3"), ("R2-FR-001", "100000"), ("NAO-EXISTE", "5"),
                 ("R2-FR-001", "5", "--reason", "abc")):
        assert run_cli("stock", *args).returncode != 0, args
    assert q(STOCK_R2_FR_001) == [(20,)]
    assert q(ADJUSTMENTS) == [(0,)]


def test_cli_reconcile_pass_and_detects_divergence(ledger_db):
    ok = run_cli("reconcile")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "PASS" in ok.stdout
    from app.db import connect
    with connect() as db:
        db.execute("UPDATE products SET stock = stock + 7 WHERE sku = 'R2-FR-002'")  # RED: sem movimento
    bad = run_cli("reconcile")
    assert bad.returncode == 2
    assert "R2-FR-002" in bad.stdout


def test_cli_fails_closed_on_legacy_db_then_migrate_fixes_it(legacy_db):
    blocked = run_cli("stock", "R2-FR-001", "30")
    assert blocked.returncode != 0
    assert "migrate" in blocked.stderr
    assert q(STOCK_R2_FR_001) == [(20,)]  # nada foi alterado
    migrated = run_cli("migrate")
    assert migrated.returncode == 0, migrated.stderr
    assert run_cli("migrate").stdout.strip() == "Nenhuma migração pendente"
    assert run_cli("stock", "R2-FR-001", "30").returncode == 0
    assert run_cli("reconcile").returncode == 0
    assert oracle_discrepancies() == []


def test_cli_rollback_requires_confirmation(ledger_db):
    assert run_cli("rollback").returncode != 0
    assert q("SELECT COUNT(*) FROM sqlite_master WHERE name='inventory_movements'") == [(1,)]
    done = run_cli("rollback", "--yes")
    assert done.returncode == 0, done.stderr
    assert q("SELECT COUNT(*) FROM sqlite_master WHERE name='inventory_movements'") == [(0,)]


def test_cli_movements_lists_history(ledger_db):
    assert run_cli("stock", "R2-FR-001", "22", "--reason", "contagem-ciclica").returncode == 0
    r = run_cli("movements", "R2-FR-001")
    assert r.returncode == 0
    assert "ADJUSTMENT" in r.stdout and "OPENING" in r.stdout
