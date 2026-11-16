# Relatório técnico — Exercício 2 (evolução do banco, Rota 2 Motopeças)

PR #1 no fork `NicolasJosedaSilva/rea-motopecas-antigravity` · branch `lab/banco-dados-opcao-a`.
Todos os números abaixo vêm dos logs em `docs/evidence/db`.

## 1. Ambiente
Windows, Python 3.14.3, SQLite 3.50.4, pytest 9.2.0.

## 2. TDD: RED e GREEN
- **RED** (código original + testes novos): 33 dos 34 testes novos falharam (19 FAILED + 14 ERROR). O único que passou foi a regressão "estoque nunca negativo", que já era garantida por CHECK. Log: `red_pytest.txt`.
- **GREEN** (com a implementação): **50 passed** em 21,54 s (16 antigos + 34 novos). Log: `green_pytest_v.txt`.
- **Gate do repositório** (`scripts/gate.py`): GATE PASS. Log: `gate.txt`.

## 3. Rollback e atomicidade
- Migração: executada em `BEGIN IMMEDIATE`; uma migração com erro no meio não deixa tabela parcial nem registro em `schema_migrations` (`test_failed_migration_is_fully_rolled_back`).
- Reversão: `migrations/001_inventory_ledger.down.sql` remove ledger, índices e triggers e preserva as quatro tabelas originais; exige `--yes`. **A reversão apaga o histórico de movimentos**; fazer backup antes.
- Pedidos e ajustes: falha ao gravar o movimento desfaz também o UPDATE do estoque e o pedido (`test_ledger_failure_rolls_back_the_whole_order`, `test_adjust_failure_leaves_no_partial_effect`).

## 4. Idempotência
Repetir um pedido com a mesma `Idempotency-Key` não cria pedido nem movimento novo (`test_idempotent_replay_creates_no_new_movements`).

## 5. FK e CHECK
`PRAGMA integrity_check = ok` e `PRAGMA foreign_key_check` vazio em todos os `verify` do laboratório. O ledger rejeita linhas inválidas (delta zero, SALE positivo, SALE sem pedido, motivo curto, produto inexistente, abertura ou venda duplicada) e não aceita UPDATE nem DELETE.

## 6. Conciliação
`verify`/`reconcile` comparam `products.stock` com a soma dos movimentos. Caso RED deliberado do laboratório: `UPDATE` direto no estoque do produto R2-FR-002 sem movimento → `{'sku': 'R2-FR-002', 'stock': 17, 'ledger_balance': 18}` e código de saída 2.

## 7. Backup e restauração (`lab_ensaio.txt`)
| Ciclo | Resultado | SHA-256 do backup |
|---|---|---|
| baseline (antes da migração) | RESTORE PASS, 12 produtos, integrity ok, FK 0, hash confere | 47d09246eaf5ac72b89c49752d247b0271e40a2776202902547d8979ac5dc5a6 |
| pós-migração | RESTORE PASS, ledger conciliado, hash confere | 738d15167c82e5725695a9889161b4ba9b26e271133f23e64f6c293a84a495c6 |

O hash do ciclo pós-migração muda a cada execução (o banco guarda horários); o valor acima é o da execução registrada em `lab_ensaio.txt`.
Um backup adulterado é recusado antes da restauração (`test_lab_restore_detects_tampered_backup`).

## 8. Segurança
- SQL parametrizado preservado; o ledger não é exposto por endpoint HTTP.
- Laboratório só aceita `lab_*.db` e nunca toca em `data/motopecas.db`.
- `data/` e `*.db` estão no `.gitignore`; nenhum banco, segredo ou dado pessoal foi publicado.
- O app não migra sozinho um banco que já tem dados.

## 9. Limites e itens NÃO VERIFICADO
- Parecer independente e aprovação humana: **NÃO VERIFICADO** (pendentes).
- CI do GitHub no fork: não executado (Checks 0); só o gate local.
- WAL: não habilitado. PostgreSQL: apenas critérios no ADR, sem migração.
- Testes executados só em Windows com Python 3.14.3; `pip-audit` não foi rodado.
- O saldo de abertura (T0) não reconstrói vendas anteriores.
- O teste de concorrência cobre dois pedidos simultâneos; não é teste de carga.
