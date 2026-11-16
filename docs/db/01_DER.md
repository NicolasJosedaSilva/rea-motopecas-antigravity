# DER — banco da Rota 2 Motopeças (SQLite, Opção A)

Gerado a partir de `app/db.py` (esquema atual) e `migrations/001_inventory_ledger.sql` (proposto/implementado).
Os diagramas usam Mermaid (renderizado pelo GitHub).

## DER atual (baseline: 4 tabelas)

```mermaid
erDiagram
    products ||--o{ compatibility : "compatível com"
    products ||--o{ order_items : "vendido em"
    orders ||--|{ order_items : "contém"
    products {
        INTEGER id PK
        TEXT sku UK
        TEXT name
        TEXT category
        TEXT image
        INTEGER price_cents "CHECK >= 0"
        INTEGER stock "CHECK >= 0"
        TEXT description
    }
    compatibility {
        INTEGER product_id PK "FK products.id"
        TEXT bike_id PK
    }
    orders {
        TEXT id PK
        TEXT idempotency_key UK
        TEXT request_digest
        INTEGER total_cents
        TEXT created_at
        TEXT status "padrão SIMULADO"
    }
    order_items {
        TEXT order_id PK "FK orders.id"
        INTEGER product_id PK "FK products.id"
        INTEGER quantity "CHECK > 0"
        INTEGER unit_price_cents
    }
```

## DER proposto e implementado (+ schema_migrations e inventory_movements)

```mermaid
erDiagram
    products ||--o{ compatibility : "compatível com"
    products ||--o{ order_items : "vendido em"
    orders ||--|{ order_items : "contém"
    products ||--o{ inventory_movements : "movimenta"
    orders ||--o{ inventory_movements : "origina SALE/RETURN"
    inventory_movements {
        INTEGER id PK
        INTEGER product_id FK "NOT NULL"
        INTEGER delta_qty "CHECK <> 0"
        TEXT movement_type "OPENING SALE ADJUSTMENT RETURN"
        TEXT order_id FK "obrigatório em SALE e RETURN"
        TEXT reason "CHECK length >= 5"
        TEXT created_at
    }
    schema_migrations {
        TEXT version PK
        TEXT applied_at
    }
```

As tabelas `products`, `compatibility`, `orders` e `order_items` não mudam.
`schema_migrations` não tem relação com as demais: só registra quais migrações foram aplicadas.

## O que a migração 001 acrescenta além das tabelas

| Objeto | Função |
|---|---|
| `ux_opening_product` (índice único parcial) | no máximo um saldo de abertura por produto |
| `ux_sale_order_product` (índice único parcial) | uma venda por par (pedido, produto) |
| `ix_movements_product`, `ix_compat_bike`, `ix_products_category` | consultas por produto, por moto e por categoria |
| `trg_inventory_movements_no_update` / `_no_delete` | ledger append-only |
