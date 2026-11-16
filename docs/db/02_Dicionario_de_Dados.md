# Dicionário de dados e invariantes

## products
| Coluna | Tipo | Restrições | Descrição |
|---|---|---|---|
| id | INTEGER | PK | identificador |
| sku | TEXT | NOT NULL, UNIQUE | código do produto (ex.: R2-FR-001) |
| name | TEXT | NOT NULL | nome |
| category | TEXT | NOT NULL | categoria (filtro RF-03) |
| image | TEXT | NOT NULL | arquivo da imagem |
| price_cents | INTEGER | NOT NULL, CHECK >= 0 | preço em centavos |
| stock | INTEGER | NOT NULL, CHECK >= 0 | saldo atual (projeção do ledger) |
| description | TEXT | NOT NULL | descrição |

## compatibility
| Coluna | Tipo | Restrições | Descrição |
|---|---|---|---|
| product_id | INTEGER | PK composta, FK products(id) | produto |
| bike_id | TEXT | PK composta, NOT NULL | moto compatível |

## orders
| Coluna | Tipo | Restrições | Descrição |
|---|---|---|---|
| id | TEXT | PK | identificador do pedido (DEMO-...) |
| idempotency_key | TEXT | NOT NULL, UNIQUE | chave que impede pedido duplicado |
| request_digest | TEXT | NOT NULL | resumo do corpo do pedido |
| total_cents | INTEGER | NOT NULL | total em centavos |
| created_at | TEXT | NOT NULL, padrão CURRENT_TIMESTAMP | criação |
| status | TEXT | NOT NULL, padrão 'SIMULADO' | status demonstrativo |

## order_items
| Coluna | Tipo | Restrições | Descrição |
|---|---|---|---|
| order_id | TEXT | PK composta, FK orders(id) | pedido |
| product_id | INTEGER | PK composta, FK products(id) | produto |
| quantity | INTEGER | NOT NULL, CHECK > 0 | quantidade |
| unit_price_cents | INTEGER | NOT NULL | preço unitário no momento do pedido |

## inventory_movements (nova)
| Coluna | Tipo | Restrições | Descrição |
|---|---|---|---|
| id | INTEGER | PK | identificador do movimento |
| product_id | INTEGER | NOT NULL, FK products(id) ON DELETE RESTRICT | produto movimentado |
| delta_qty | INTEGER | NOT NULL, CHECK <> 0 | variação (negativa em venda) |
| movement_type | TEXT | NOT NULL, CHECK em OPENING/SALE/ADJUSTMENT/RETURN | tipo |
| order_id | TEXT | FK orders(id) ON DELETE RESTRICT | pedido de origem |
| reason | TEXT | NOT NULL, CHECK length(trim) >= 5 | motivo |
| created_at | TEXT | NOT NULL, padrão CURRENT_TIMESTAMP | momento |

Regras por tipo (CHECK da tabela): OPENING exige delta > 0 e sem pedido; ADJUSTMENT não tem pedido;
SALE exige delta < 0 e pedido; RETURN exige delta > 0 e pedido.

## schema_migrations (nova)
| Coluna | Tipo | Restrições | Descrição |
|---|---|---|---|
| version | TEXT | PK | ex.: 001_inventory_ledger |
| applied_at | TEXT | NOT NULL, padrão CURRENT_TIMESTAMP | quando foi aplicada |

## Invariantes (linguagem natural)
- **INV-DB-01 (conciliação):** para cada produto, `products.stock` é igual à soma de `delta_qty` dos movimentos, desde o saldo de abertura (T0). Não é uma constraint automática; é verificada por `reconcile`/`verify`.
- **INV-DB-02 (mesma transação):** toda variação de `products.stock` feita pelo app grava o movimento na mesma transação.
- **INV-DB-03 (estoque não negativo):** `products.stock >= 0`, garantido por CHECK.
- **INV-DB-04 (ledger imutável):** movimentos não são editados nem apagados; correções são novos movimentos.
- **INV-DB-05 (abertura única):** cada produto tem no máximo um movimento OPENING.
- **INV-DB-06 (idempotência):** repetir um pedido com a mesma Idempotency-Key não cria pedido nem movimento novo.
- **INV-DB-07 (T0):** o ledger começa no estoque do momento da migração e não reconstrói vendas anteriores.
