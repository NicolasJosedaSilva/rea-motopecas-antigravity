"""Exercício 2 — G-DB1/3/4/5 pelo caminho da API: pedidos geram movimentos SALE na mesma transação."""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from ledger_support import oracle_discrepancies, q


def order(client, items, key=None):
    return client.post("/api/orders", json={"items": items}, headers={"Idempotency-Key": key or str(uuid.uuid4())})


def test_order_registers_sale_movements_and_reconciles(client):
    r = order(client, [{"product_id": 1, "quantity": 2}, {"product_id": 3, "quantity": 1}])
    assert r.status_code == 201, r.text
    rows = q("SELECT product_id, delta_qty, movement_type FROM inventory_movements "
             "WHERE order_id = ? ORDER BY product_id", (r.json()["order_id"],))
    assert rows == [(1, -2, "SALE"), (3, -1, "SALE")]
    assert oracle_discrepancies() == []


def test_idempotent_replay_creates_no_new_movements(client):
    key = str(uuid.uuid4())
    body = [{"product_id": 3, "quantity": 2}]
    assert order(client, body, key).status_code == 201
    movements = q("SELECT COUNT(*) FROM inventory_movements")
    replay = order(client, body, key)
    assert replay.status_code == 201 and replay.json()["replayed"] is True
    assert q("SELECT COUNT(*) FROM inventory_movements") == movements
    assert q("SELECT COUNT(*) FROM inventory_movements WHERE movement_type='SALE'") == [(1,)]
    assert oracle_discrepancies() == []


def test_rejected_order_creates_no_movements(client):
    movements = q("SELECT COUNT(*) FROM inventory_movements")
    assert order(client, [{"product_id": 12, "quantity": 10}]).status_code == 409  # só há 8 unidades
    assert q("SELECT COUNT(*) FROM inventory_movements") == movements
    assert oracle_discrepancies() == []


def test_ledger_failure_rolls_back_the_whole_order(client, monkeypatch):
    """G-DB3: falha no meio do pedido não deixa estoque, pedido, itens ou movimentos parciais."""
    import app.main as main_module
    products = q("SELECT id, stock FROM products ORDER BY id")
    movements = q("SELECT COUNT(*) FROM inventory_movements")
    real, calls = main_module.record_movement, {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:  # falha no segundo item, depois do primeiro já ter sido gravado
            raise RuntimeError("falha simulada no ledger")
        return real(*args, **kwargs)

    monkeypatch.setattr(main_module, "record_movement", flaky)
    with pytest.raises(RuntimeError):
        order(client, [{"product_id": 1, "quantity": 1}, {"product_id": 2, "quantity": 1}])
    assert calls["n"] == 2
    assert q("SELECT id, stock FROM products ORDER BY id") == products
    assert q("SELECT COUNT(*) FROM inventory_movements") == movements
    assert q("SELECT COUNT(*) FROM orders") == [(0,)]
    assert q("SELECT COUNT(*) FROM order_items") == [(0,)]
    assert oracle_discrepancies() == []


def test_concurrent_orders_cannot_oversell(client):
    """Dois pedidos simultâneos de 3 unidades para 5 em estoque: um vence, o outro recebe 409."""
    from app.db import connect
    from app.ledger import adjust_stock
    from app.main import make_app
    with connect() as db:
        adjust_stock(db, "R2-FR-001", 5, "preparar teste de concorrencia")

    def place(_):
        local = TestClient(make_app())  # cliente independente por thread (sem lifespan)
        return order(local, [{"product_id": 1, "quantity": 3}]).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(place, range(2)))
    assert codes == [201, 409]
    assert q("SELECT stock FROM products WHERE id = 1") == [(2,)]
    assert q("SELECT COUNT(*) FROM inventory_movements WHERE movement_type='SALE'") == [(1,)]
    assert oracle_discrepancies() == []
