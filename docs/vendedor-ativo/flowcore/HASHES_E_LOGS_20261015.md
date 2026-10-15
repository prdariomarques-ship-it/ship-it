# Artefatos recebidos, patches e logs — 15/10/2026

Todos os resultados abaixo são **do autor, em sandbox** (dados sintéticos, PostgreSQL 16.13 descartável em loopback, removido ao final). Não foi aplicado nada na VPS.

## Artefatos recebidos (SHA-256 completo)
| Arquivo | SHA-256 |
|---|---|
| `flowcore-integration-proposal-v2_3.patch` | `57c2259accfdb544bea8e4ff30b0b54a1c839dafddc8c3c1742006161b9595f9` |
| `base_hash_confirmed_25files.zip` | `fb41b368ea7e5d4dbdb654895e13a59044a712931fe9a3e9724cdc86858ef3cf` |
| `flowcore-test-source-snapshot-20261015.zip` | `b62b21b16ddd7b69339b83d4245f78651df851b47b63b4667980686559b156fe` |
| `ship-it-source-candidates-20261015_3.zip` = `_4.zip` (idênticos) | `4d3c5199d26df56da8512b8359e1ae65d64b724922e5c74a34a95813aea92977` |

## Patches produzidos (ordem: base → store_sales da base → v2_3 → patch 2 → patch 3)
| Patch | SHA-256 | O que muda |
|---|---|---|
| patch 2 (`patch2-testes-sqlite-e-migration.patch`) | `1e80e3debcf96f2d4f0c5f23cf2d32113aca93e138542cbefc1bd7a24d20515a` | só testes (superado em parte pelo patch 3: ver LEIA-ME) |
| patch 3 (`patch3-claim-on-conflict-e-migration-completa.patch`) | `02b3f9cf5e6e6ab5162875002d14681322745b6949b272c10418ee6b267456a5` | **muda código de produção**: `_claim_key` passa a usar `INSERT … ON CONFLICT DO NOTHING RETURNING` (PostgreSQL e SQLite; outros bancos mantêm o caminho antigo com SAVEPOINT) + testes |

## Execução (árvore: snapshot + 9 módulos do pacote _4 + `store_sales.py` da base + `389bdd08a97f` da base + v2_3 + patch 2 + patch 3)
- `saidas/sqlite_20261015.txt`: **18 passam, 0 falham, 0 xfail** (`test_flowcore_integration.py` + `test_store_migration.py`).
- `saidas/postgres_20261015.txt`: **11 passam**: 9 do harness de concorrência (6 originais + falha tardia com rollback conjunto + resposta perdida + chave reutilizada com outro corpo) e 2 da cadeia de migrations (`alembic upgrade head` do banco vazio, esquema histórico escrito à mão, linhas preservadas no upgrade/downgrade, reupgrade).
- `synchronize_session=False` no `store_sales.py` usado: **1 ocorrência(s)** (veio da base confirmada; o patch não o toca).
- Mutações (todas reprovadas): sem `ON CONFLICT` (SQLite 2 + PG 2 falham); recibo confirmado logo após o claim (SQLite 5 + PG 4); duplicata sem conferir o hash do corpo (SQLite 2, PG 1); downgrade que não remove a coluna (2); upgrade que apaga orçamentos (1); downgrade que apaga orçamentos (1).

## Achados que mudam conclusões anteriores
1. **A cópia portátil não tem a migration `389bdd08a97f`** (cadeia quebrada: `a1f9c3d84e2b` depende dela). Está na base de 25 arquivos (hash conferido). Os testes de cadeia completa exigem essa migration na árvore.
2. Com `ON CONFLICT` no claim, o recibo **deixa de depender de SAVEPOINT**: no SQLite em modo antigo, recibo, contato, cliente e orçamento passam a sumir juntos no rollback (teste `test_legacy_sqlite_failure_after_…`). Isto é mudança de **comportamento do código**, não só de teste. O SAVEPOINT da criação de contato permanece.
3. Os números do revisor (11/13 e 6/6) não são os desta árvore: aqui o conjunto SQLite tem 18 testes e o harness de PostgreSQL tem 9 (+2 de migration).
