# ADR-001 — Manter SQLite e evoluir o esquema; PostgreSQL só com critérios mensuráveis

- **Status:** proposto pela equipe (aguarda parecer independente e aprovação humana)
- **Data:** 16/11/2026

## Contexto
A Rota 2 Motopeças é uma aplicação didática local (FastAPI + SQLite, quatro tabelas, sem pagamentos reais).
O Exercício 2 pede evolução versionada e auditável, sem exigir a troca imediata do SGBD.

## Decisão
1. **Manter o SQLite** como banco da Opção A.
2. Evoluir por migrações SQL versionadas (`migrations/NNN_*.sql` com `.down.sql`) e ledger de estoque.
3. **Não habilitar WAL** por enquanto. O ambiente usa SQLite 3.50.4, e o material da disciplina cita uma correção de WAL em 3.51.3; essa informação não foi verificada de forma independente pela equipe.
4. Documentar quando migrar para PostgreSQL (critérios abaixo), sem executar a migração.

## Alternativas consideradas
| Opção | Prós | Contras |
|---|---|---|
| Manter SQLite (escolhida) | zero infraestrutura, arquivo único, backup via API do SQLite, suficiente para o protótipo | um escritor por vez; sem papéis de acesso por usuário |
| Migrar já para PostgreSQL | concorrência de escrita, papéis, replicação | exige servidor, credenciais e infraestrutura que o laboratório não precisa |

## Critérios para reavaliar (propostos; a equipe deve validar os números)
Considerar PostgreSQL quando **qualquer** item ocorrer de forma recorrente:
- mais de um processo/servidor escrevendo ao mesmo tempo, com erros `database is locked` ou esperas acima de `busy_timeout` (15 s) em testes de carga;
- necessidade de papéis separados (leitura, escrita, administração) ou auditoria por usuário;
- necessidade de replicação, alta disponibilidade ou recuperação até um ponto no tempo;
- dados reais de clientes (LGPD) ou volume que torne o backup completo do arquivo lento demais;
- uso fora do ambiente local/didático.

## Consequências
- O modelo (ledger, invariantes, migrações) é portável: usa SQL padrão, exceto `RAISE` em triggers e o formato de datas, que teriam de ser adaptados.
- A migração ao PostgreSQL continua sendo trabalho futuro e **não foi testada**.
- Mantêm-se os controles atuais: SQL parametrizado, banco `lab_*.db` isolado, `data/` e `*.db` no `.gitignore`.
