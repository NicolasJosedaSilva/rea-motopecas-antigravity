-- Reversão da migração 001. ATENÇÃO: apaga o histórico de movimentos.
-- Faça backup antes (python scripts/lab_db_extension.py backup ...).
-- Não altera products, orders, order_items nem compatibility (dados preservados).

DROP TRIGGER IF EXISTS trg_inventory_movements_no_update;
DROP TRIGGER IF EXISTS trg_inventory_movements_no_delete;
DROP INDEX IF EXISTS ix_products_category;
DROP INDEX IF EXISTS ix_compat_bike;
DROP INDEX IF EXISTS ix_movements_product;
DROP INDEX IF EXISTS ux_sale_order_product;
DROP INDEX IF EXISTS ux_opening_product;
DROP TABLE IF EXISTS inventory_movements;
