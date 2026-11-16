# Matriz requisito → tabela → teste → gate

Evidência geral: `docs/evidence/db/green_pytest_v.txt` (50 passed) e `docs/evidence/db/red_pytest.txt`.
Nomes de teste referem-se aos arquivos em `tests/`. Gates: G-DB1 conciliação · G-DB2 integridade · G-DB3 rollback · G-DB4 idempotência · G-DB5 API e CLI.

| Requisito | Tabela / objeto | Teste(s) | Gate |
|---|---|---|---|
| RQ-DB-01 Histórico de movimentos com saldo de abertura (T0) | inventory_movements | test_migration_001_is_additive_and_records_opening_balance; test_fresh_initialize_applies_migration_and_opening_balance | G-DB1 |
| RQ-DB-02 Migração aditiva e idempotente | schema_migrations | test_migration_is_idempotent; test_migration_does_not_reconstruct_past_sales | G-DB1 |
| RQ-DB-03 Falha na migração não deixa efeito parcial | schema_migrations | test_failed_migration_is_fully_rolled_back | G-DB3 |
| RQ-DB-04 Migração reversível (down), com confirmação | schema_migrations | test_rollback_restores_baseline_and_preserves_data; test_cli_rollback_requires_confirmation; test_lab_rollback_requires_confirmation | G-DB3 |
| RQ-DB-05 Banco com dados não migra sozinho (falha fechado) | schema_migrations | test_initialize_fails_closed_when_migration_is_pending; test_cli_fails_closed_on_legacy_db_then_migrate_fixes_it | controle adicional |
| RQ-DB-06 Conciliação detecta divergência (caso RED) | products, inventory_movements | test_red_stock_update_without_movement_is_detected; test_cli_reconcile_pass_and_detects_divergence; test_lab_verify_detects_divergence | G-DB1 |
| RQ-DB-07 Pedido grava SALE na mesma transação | orders, order_items, inventory_movements | test_order_registers_sale_movements_and_reconciles | G-DB5 (API) |
| RQ-DB-08 Falha no ledger desfaz o pedido/ajuste inteiro | orders, order_items, products, inventory_movements | test_ledger_failure_rolls_back_the_whole_order; test_adjust_failure_leaves_no_partial_effect | G-DB3 |
| RQ-DB-09 Repetir a Idempotency-Key não duplica movimento | orders, inventory_movements | test_idempotent_replay_creates_no_new_movements | G-DB4 |
| RQ-DB-10 Ajuste pela CLI grava ADJUSTMENT com motivo | products, inventory_movements | test_cli_stock_registers_adjustment_movement; test_cli_stock_without_reason_keeps_old_usage; test_adjust_stock_writes_movement_in_same_transaction | G-DB5 (CLI) |
| RQ-DB-11 Estoque nunca negativo e sem venda em excesso | products | test_stock_never_negative_at_database_level; test_concurrent_orders_cannot_oversell; test_rejected_order_creates_no_movements | G-DB3 |
| RQ-DB-12 Constraints do ledger (CHECK, FK, UNIQUE) | inventory_movements | test_ledger_constraints_reject_invalid_rows | G-DB2 |
| RQ-DB-13 Ledger imutável | inventory_movements (triggers) | test_ledger_is_append_only | G-DB2 |
| RQ-DB-14 Entradas inválidas não gravam nada | products, inventory_movements | test_adjust_rejects_invalid_input_without_writing; test_cli_rejects_invalid_input_without_writing | G-DB3 |
| RQ-DB-15 Backup com SHA-256 e restauração validada | arquivo lab_*.db | test_lab_full_sequence_with_two_backup_restore_cycles; test_lab_backup_refuses_overwrite_and_records_hash; test_lab_restore_detects_tampered_backup | G-DB2 |
| RQ-DB-16 Laboratório só em lab_*.db | arquivo lab_*.db | test_lab_refuses_non_lab_database | segurança |
| RQ-DB-17 Contratos originais da API e da CLI preservados | todas | tests/test_api.py (13 testes) e tests/test_cli.py (3 testes) | regressão |
