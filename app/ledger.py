"""Livro-razão de estoque: toda variação de products.stock gera um movimento.

Invariante INV-DB-01: para cada produto, products.stock = SUM(delta_qty) dos
movimentos desde o saldo de abertura (T0). O UPDATE do estoque e o INSERT do
movimento devem ocorrer na MESMA transação (quem chama controla o COMMIT).
"""
from __future__ import annotations

import sqlite3

MAX_STOCK = 99999
MIN_REASON = 5


class LedgerUnavailable(RuntimeError):
    """A migração 001 ainda não foi aplicada neste banco."""


def has_ledger(db: sqlite3.Connection) -> bool:
    row = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_movements'").fetchone()
    return row is not None


def record_movement(db: sqlite3.Connection, product_id: int, delta_qty: int, movement_type: str,
                    reason: str, order_id: str | None = None) -> None:
    """INSERT de um movimento. NÃO abre nem fecha transação."""
    db.execute(
        "INSERT INTO inventory_movements (product_id, delta_qty, movement_type, order_id, reason) "
        "VALUES (?,?,?,?,?)",
        (product_id, delta_qty, movement_type, order_id, reason),
    )


def adjust_stock(db: sqlite3.Connection, sku: str, quantity: int, reason: str) -> tuple[int, int, int]:
    """Define o estoque de um SKU e registra o movimento ADJUSTMENT. Retorna (antes, depois, delta)."""
    if not isinstance(quantity, int) or not (0 <= quantity <= MAX_STOCK):
        raise ValueError(f"Quantidade inválida (0-{MAX_STOCK})")
    if not reason or len(reason.strip()) < MIN_REASON:
        raise ValueError(f"Motivo obrigatório (mínimo {MIN_REASON} caracteres)")
    if not has_ledger(db):
        raise LedgerUnavailable("Migração 001 não aplicada neste banco")
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT id, stock FROM products WHERE sku=?", (sku,)).fetchone()
        if row is None:
            raise LookupError("SKU não encontrado")
        before, delta = row[1], quantity - row[1]
        if delta:
            db.execute("UPDATE products SET stock=? WHERE id=?", (quantity, row[0]))
            record_movement(db, row[0], delta, "ADJUSTMENT", reason.strip())
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    return before, quantity, delta


def reconcile(db: sqlite3.Connection) -> list[dict]:
    """Divergências entre products.stock e a soma dos movimentos (lista vazia = conciliado)."""
    rows = db.execute(
        "SELECT p.sku, p.stock, COALESCE(SUM(m.delta_qty), 0) AS ledger_balance "
        "FROM products p LEFT JOIN inventory_movements m ON m.product_id = p.id "
        "GROUP BY p.id HAVING p.stock <> COALESCE(SUM(m.delta_qty), 0) ORDER BY p.sku"
    ).fetchall()
    return [{"sku": r[0], "stock": r[1], "ledger_balance": r[2]} for r in rows]


def movements_for(db: sqlite3.Connection, sku: str, limit: int = 50) -> list[dict]:
    rows = db.execute(
        "SELECT m.id, m.movement_type, m.delta_qty, m.order_id, m.reason, m.created_at "
        "FROM inventory_movements m JOIN products p ON p.id = m.product_id "
        "WHERE p.sku = ? ORDER BY m.id DESC LIMIT ?",
        (sku, limit),
    ).fetchall()
    return [
        {"id": r[0], "type": r[1], "delta_qty": r[2], "order_id": r[3], "reason": r[4], "created_at": r[5]}
        for r in rows
    ]


def check(db: sqlite3.Connection) -> dict:
    """Relatório de integridade: PRAGMAs + conciliação. 'ledger' = False se não migrado."""
    report = {
        "sqlite_version": sqlite3.sqlite_version,
        "integrity_check": db.execute("PRAGMA integrity_check").fetchone()[0],
        "foreign_key_violations": len(db.execute("PRAGMA foreign_key_check").fetchall()),
        "ledger": has_ledger(db),
        "discrepancies": [],
    }
    if report["ledger"]:
        report["discrepancies"] = reconcile(db)
    report["ok"] = (
        report["integrity_check"] == "ok"
        and report["foreign_key_violations"] == 0
        and report["ledger"]
        and not report["discrepancies"]
    )
    return report
