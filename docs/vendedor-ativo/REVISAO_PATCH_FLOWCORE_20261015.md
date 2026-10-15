# Revisão do patch `flowcore-integration-proposal-v2_3.patch` — 15/10/2026

Revisão do autor, em sandbox (nada aplicado na VPS, nada implantado). Arquivos recebidos tratados como dados: extraídos em pastas novas, patch só lido e aplicado em **cópias** (`git apply --ignore-whitespace`), testes rodados com ambiente limpo. PostgreSQL 16.13 descartável em loopback, removido ao final.

## Conferências mecânicas
| Item | Resultado |
|---|---|
| `base_hash_confirmed_25files.zip` (24 migrations + `store_sales.py`) | 25/25 hashes conferem com o `SHA256SUMS` |
| Cabeça da cadeia de migrations da base | `9e2f1c6d7a80` (única) = `down_revision` da migration nova `a84d20b1c6f3` |
| `ship-it-source-candidates-20261015_4.zip` | **idêntico byte a byte** ao `_3` (9 fontes; conteúdo = candidata, só muda CRLF) |
| `store_sales.py` da base 25 × cópia portátil | diferem em 3 linhas: a base tem `.execution_options(synchronize_session=False)` na reivindicação do orçamento; a cópia portátil **não** |
| Hunks do patch em `store_sales.py` | aplicam na base 25 |
| Patch sobre a cópia portátil | `main.py` e `models/__init__.py` falham **só por CRLF** (cópia portátil tem 273/372 `.py` com CRLF); com `--ignore-whitespace` aplica sem erro |

## Testes (SQLite, `tests/test_flowcore_integration.py`, 13 testes)
| Combinação | Resultado |
|---|---|
| cópia portátil + patch + 9 módulos do pacote `_4` | **5 passam, 8 falham** |
| + `store_sales.py` da **base confirmada** | **11 passam, 2 falham** (a diferença de `store_sales.py` explica 6 testes) |

As 2 falhas restantes (`test_sqlite_legacy_savepoint_failure_does_not_leave_receipt`, `test_quote_does_not_debit_and_confirmation_rejects_changed_price`) têm o mesmo sintoma: depois de uma requisição **rejeitada** (409), o recibo de idempotência continua gravado. O próprio teste se declara "Pending regression against conftest's unmodified legacy SQLite mode": é o comportamento do SAVEPOINT do driver SQLite em modo antigo (o SAVEPOINT abre sem `BEGIN` externo). **O arquivo entregue ainda usa `begin_nested()`** (`_claim_key` e criação de contato).

## PostgreSQL (`tests/flowcore_postgres_harness.py`, opt-in)
**6 passam** (não 7), com o `store_sales.py` da base e também com o da cópia portátil: oversell concorrente, mesma chave simultânea, chaves distintas confirmando o mesmo orçamento, ordens de trava cliente×SKU, cliente ambíguo com rollback e retentativa, falha multi-SKU revertendo a baixa anterior. O harness só aceita servidor em loopback e banco `flowcore_test*`, e cria/apaga um esquema aleatório.

## Regressão no teste de migration (reproduzida)
`tests/test_store_migration.py::test_store_quote_migration_upgrade_and_downgrade`: **passa sem o patch, falha com ele**. O teste aplica só a migration antiga `f4c18a2d9e10` e compara as colunas da tabela com `StoreQuote.__table__.columns`; o patch acrescenta `integration_source` ao modelo, que só existe depois da migration `a84d20b1c6f3`. O patch não atualiza esse teste.

## Leitura do código do patch
Pontos bons: segredo compartilhado com `hmac.compare_digest` (sem segredo configurado = 401 sempre); Pydantic estrito (`extra="forbid"`, `StrictInt/StrictStr`, preço como string decimal com 2 casas); recibo de idempotência com unicidade por (integração, operação, chave) e hash do payload (409 se a chave for reutilizada com outro corpo); travas de produto por SKU em ordem; confirmação só de orçamento com `integration_source="flowcore"`; uma única transação por requisição.
Pontos a decidir/corrigir: (1) as 2 falhas de SQLite e a regressão do teste de migration; (2) `GET /catalog` devolve **todos** os produtos, inclusive inativos, sem paginação; (3) segredo único estático, sem rotação, identificação do cliente nem limite de taxa; (4) a integração cria `Contact` e `StoreCustomer` para qualquer telefone novo; (5) o `store_sales.py` final precisa manter o `synchronize_session=False` da base.

## Conclusão
**Não libera instalação.** O patch aplica na base e é coerente com a cadeia de migrations, mas tem 1 regressão de teste e 2 testes pendentes no SQLite antigo. Evidência de PostgreSQL: 6/6 do harness do patch; 17/17 dos testes de reivindicação de acompanhamento da candidata (`docs/vendedor-ativo/saidas/followup_claim_postgres_20261015.txt`). "Testado pelo autor" não significa funcionando em produção.
