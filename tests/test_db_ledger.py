"""Exercício 2 — ledger de estoque na camada de dados: migração 001, invariantes e rollback."""
import sqlite3

import pytest

from ledger_support import (  # noqa: F401  (fixtures e utilitários)
    ledger, ledger_db, legacy_db, migrations, oracle_discrepancies, q,
)

ORIGINAL_TABLES = {"compatibility", "order_items", "orders", "products"}


def table_names():
    return {r[0] for r in q("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def test_baseline_has_four_tables_and_no_ledger(legacy_db):
    assert table_names() == ORIGINAL_TABLES
    assert q("SELECT COUNT(*) FROM products") == [(12,)]


def test_migration_001_is_additive_and_records_opening_balance(legacy_db, migrations):
    from app.db import connect
    before = {t: q(f"SELECT * FROM {t} ORDER BY 1, 2") for t in sorted(ORIGINAL_TABLES)}
    with connect() as db:
        assert migrations.apply_pending(db) == ["001_inventory_ledger"]
    assert {t: q(f"SELECT * FROM {t} ORDER BY 1, 2") for t in sorted(ORIGINAL_TABLES)} == before
    assert table_names() == ORIGINAL_TABLES | {"inventory_movements", "schema_migrations"}
    assert q("SELECT version FROM schema_migrations") == [("001_inventory_ledger",)]
    assert q("SELECT COUNT(*), SUM(delta_qty) FROM inventory_movements WHERE movement_type='OPENING'") == \
        q("SELECT COUNT(*), SUM(stock) FROM products WHERE stock > 0")
    assert oracle_discrepancies() == []


def test_migration_is_idempotent(legacy_db, migrations):
    from app.db import connect
    with connect() as db:
        assert migrations.apply_pending(db) == ["001_inventory_ledger"]
        snapshot = q("SELECT * FROM inventory_movements ORDER BY id")
        assert migrations.apply_pending(db) == []
    assert q("SELECT COUNT(*) FROM schema_migrations") == [(1,)]
    assert q("SELECT * FROM inventory_movements ORDER BY id") == snapshot


def test_migration_does_not_reconstruct_past_sales(legacy_db, migrations):
    """Pedido anterior à migração é preservado; o ledger começa no estoque ATUAL (T0)."""
    from app.db import connect
    with connect() as db:
        db.execute("INSERT INTO orders(id,idempotency_key,request_digest,total_cents) VALUES ('DEMO-LEGADO','chave-legado-1','x',9180)")
        db.execute("INSERT INTO order_items(order_id,product_id,quantity,unit_price_cents) VALUES ('DEMO-LEGADO',1,2,4590)")
        db.execute("UPDATE products SET stock = stock - 2 WHERE id = 1")
        migrations.apply_pending(db)
    assert q("SELECT COUNT(*) FROM orders") == [(1,)]
    assert q("SELECT COUNT(*) FROM order_items") == [(1,)]
    assert q("SELECT delta_qty FROM inventory_movements WHERE product_id=1") == [(18,)]
    assert q("SELECT COUNT(*) FROM inventory_movements WHERE movement_type='SALE'") == [(0,)]
    assert oracle_discrepancies() == []


def test_fresh_initialize_applies_migration_and_opening_balance(ledger_db, ledger):
    from app.db import connect
    assert q("SELECT COUNT(*) FROM inventory_movements WHERE movement_type='OPENING'") == [(12,)]
    assert oracle_discrepancies() == []
    with connect() as db:
        report = ledger.check(db)
    assert report["ok"] is True
    assert (report["integrity_check"], report["foreign_key_violations"], report["ledger"]) == ("ok", 0, True)


def test_red_stock_update_without_movement_is_detected(ledger_db, ledger):
    """Caso RED deliberado: alterar stock sem movimento deve ser acusado pela conciliação."""
    from app.db import connect
    with connect() as db:
        db.execute("UPDATE products SET stock = stock - 1 WHERE sku = 'R2-FR-001'")
        found = ledger.reconcile(db)
        assert ledger.check(db)["ok"] is False
    assert found == [{"sku": "R2-FR-001", "stock": 19, "ledger_balance": 20}]
    assert oracle_discrepancies() == [("R2-FR-001",)]


def test_adjust_stock_writes_movement_in_same_transaction(ledger_db, ledger):
    from app.db import connect
    with connect() as db:
        assert ledger.adjust_stock(db, "R2-FR-001", 25, "inventario-aula") == (20, 25, 5)
        assert ledger.adjust_stock(db, "R2-FR-001", 25, "sem alteracao") == (25, 25, 0)  # sem delta: sem movimento
    assert q("SELECT movement_type, delta_qty, reason FROM inventory_movements WHERE movement_type='ADJUSTMENT'") == \
        [("ADJUSTMENT", 5, "inventario-aula")]
    assert q("SELECT stock FROM products WHERE sku='R2-FR-001'") == [(25,)]
    assert oracle_discrepancies() == []


def test_adjust_failure_leaves_no_partial_effect(ledger_db, ledger, monkeypatch):
    """G-DB3: se o INSERT do movimento falha, o UPDATE do estoque também é desfeito."""
    from app.db import connect

    def boom(*args, **kwargs):
        raise RuntimeError("falha simulada no ledger")

    monkeypatch.setattr(ledger, "record_movement", boom)
    movements_before = q("SELECT COUNT(*) FROM inventory_movements")
    with connect() as db:
        with pytest.raises(RuntimeError):
            ledger.adjust_stock(db, "R2-FR-001", 99, "teste de rollback")
        assert not db.in_transaction
    assert q("SELECT stock FROM products WHERE sku='R2-FR-001'") == [(20,)]
    assert q("SELECT COUNT(*) FROM inventory_movements") == movements_before
    assert oracle_discrepancies() == []


def test_adjust_rejects_invalid_input_without_writing(ledger_db, ledger):
    from app.db import connect
    movements_before = q("SELECT COUNT(*) FROM inventory_movements")
    with connect() as db:
        for args, exc in [
            (("R2-FR-001", -1, "motivo valido"), ValueError),
            (("R2-FR-001", 100000, "motivo valido"), ValueError),
            (("R2-FR-001", 5, "abc"), ValueError),
            (("NAO-EXISTE", 5, "motivo valido"), LookupError),
        ]:
            with pytest.raises(exc):
                ledger.adjust_stock(db, *args)
            assert not db.in_transaction
    assert q("SELECT stock FROM products WHERE sku='R2-FR-001'") == [(20,)]
    assert q("SELECT COUNT(*) FROM inventory_movements") == movements_before


def test_ledger_is_append_only(ledger_db, ledger):
    from app.db import connect
    with connect() as db:
        ledger.adjust_stock(db, "R2-FR-001", 21, "correcao de inventario")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE inventory_movements SET delta_qty = 999")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM inventory_movements")
    assert oracle_discrepancies() == []


def test_ledger_constraints_reject_invalid_rows(ledger_db):
    from app.db import connect
    insert = ("INSERT INTO inventory_movements(product_id,delta_qty,movement_type,order_id,reason) "
              "VALUES (?,?,?,?,?)")
    invalid = [
        (1, 0, "ADJUSTMENT", None, "delta zero nao permitido"),
        (1, 5, "SALE", "DEMO-T1", "venda com delta positivo"),
        (1, -5, "SALE", None, "venda sem pedido"),
        (1, -5, "ADJUSTMENT", "DEMO-T1", "ajuste nao tem pedido"),
        (1, 5, "ADJUSTMENT", None, "abc"),
        (999, 5, "ADJUSTMENT", None, "produto inexistente"),
        (1, 5, "OPENING", None, "abertura duplicada"),
        (1, 5, "XPTO", None, "tipo desconhecido"),
    ]
    with connect() as db:
        db.execute("INSERT INTO orders(id,idempotency_key,request_digest,total_cents) VALUES ('DEMO-T1','chave-teste-1','x',0)")
        for row in invalid:
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(insert, row)
        sale = (1, -1, "SALE", "DEMO-T1", "pedido demonstrativo")
        db.execute(insert, sale)
        with pytest.raises(sqlite3.IntegrityError):  # mesma venda (pedido, produto) duas vezes
            db.execute(insert, sale)


def test_stock_never_negative_at_database_level(ledger_db):
    from app.db import connect
    with connect() as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE products SET stock = -1 WHERE id = 1")


def test_failed_migration_is_fully_rolled_back(legacy_db, migrations, tmp_path):
    from app.db import connect
    folder = tmp_path / "migracoes_ruins"
    folder.mkdir()
    (folder / "001_ruim.sql").write_text(
        "CREATE TABLE t_parcial (x INTEGER);\nCREATE TABLE t_parcial (x INTEGER);\n", encoding="utf-8")
    with connect() as db:
        with pytest.raises(sqlite3.OperationalError):
            migrations.apply_pending(db, directory=folder)
        assert not db.in_transaction
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='t_parcial'").fetchone() is None
        assert migrations.applied(db) == []


def test_rollback_restores_baseline_and_preserves_data(legacy_db, migrations, ledger):
    from app.db import connect
    before = {t: q(f"SELECT * FROM {t} ORDER BY 1, 2") for t in sorted(ORIGINAL_TABLES)}
    with connect() as db:
        assert migrations.apply_pending(db) == ["001_inventory_ledger"]
        assert migrations.rollback_last(db) == "001_inventory_ledger"
        assert not ledger.has_ledger(db)
        assert migrations.applied(db) == []
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'ix_movements%' OR name LIKE 'ux_%' "
                          "OR name IN ('ix_compat_bike','ix_products_category')").fetchone()[0] == 0
        assert migrations.apply_pending(db) == ["001_inventory_ledger"]  # reaplicável depois da reversão
    assert {t: q(f"SELECT * FROM {t} ORDER BY 1, 2") for t in sorted(ORIGINAL_TABLES)} == before
    assert oracle_discrepancies() == []


def test_initialize_fails_closed_when_migration_is_pending(legacy_db, migrations, ledger):
    """Banco com dados e migração pendente: o app não migra sozinho nem cria tabelas."""
    from app.db import connect, initialize
    with pytest.raises(migrations.MigrationPending):
        initialize()
    with connect() as db:
        assert not ledger.has_ledger(db)
        assert migrations.applied(db) == []
