-- Migração 001: livro-razão de estoque (inventory_movements). ADITIVA.
-- Aplicada por app/migrations.py dentro de BEGIN IMMEDIATE; a tabela
-- schema_migrations é criada pelo executor. Não altera products, orders,
-- order_items nem compatibility (somente cria índices auxiliares).
--
-- Invariante INV-DB-01: products.stock = SUM(inventory_movements.delta_qty)
-- por produto, DESDE o saldo de abertura (T0) registrado abaixo.

CREATE TABLE inventory_movements (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    delta_qty INTEGER NOT NULL CHECK (delta_qty <> 0),
    movement_type TEXT NOT NULL CHECK (movement_type IN ('OPENING','SALE','ADJUSTMENT','RETURN')),
    order_id TEXT REFERENCES orders(id) ON DELETE RESTRICT,
    reason TEXT NOT NULL CHECK (length(trim(reason)) >= 5),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (movement_type = 'OPENING'    AND delta_qty > 0 AND order_id IS NULL)
        OR (movement_type = 'ADJUSTMENT' AND order_id IS NULL)
        OR (movement_type = 'SALE'       AND delta_qty < 0 AND order_id IS NOT NULL)
        OR (movement_type = 'RETURN'     AND delta_qty > 0 AND order_id IS NOT NULL)
    )
);

-- Um único saldo de abertura por produto; uma única venda por (pedido, produto).
CREATE UNIQUE INDEX ux_opening_product ON inventory_movements(product_id) WHERE movement_type = 'OPENING';
CREATE UNIQUE INDEX ux_sale_order_product ON inventory_movements(order_id, product_id) WHERE movement_type = 'SALE';
CREATE INDEX ix_movements_product ON inventory_movements(product_id, id);

-- Índices de consulta do catálogo (filtro por moto e por categoria).
CREATE INDEX ix_compat_bike ON compatibility(bike_id, product_id);
CREATE INDEX ix_products_category ON products(category, id);

-- Ledger imutável (append-only): correções são novos movimentos, nunca edição.
CREATE TRIGGER trg_inventory_movements_no_update
BEFORE UPDATE ON inventory_movements
BEGIN
    SELECT RAISE(ABORT, 'inventory_movements é append-only: UPDATE proibido');
END;

CREATE TRIGGER trg_inventory_movements_no_delete
BEFORE DELETE ON inventory_movements
BEGIN
    SELECT RAISE(ABORT, 'inventory_movements é append-only: DELETE proibido');
END;

-- Saldo de abertura (T0): fotografia do estoque no instante da migração.
-- NÃO reconstrói vendas anteriores.
INSERT INTO inventory_movements (product_id, delta_qty, movement_type, reason)
SELECT id, stock, 'OPENING', 'saldo de abertura (T0) na migração 001'
FROM products
WHERE stock > 0;
