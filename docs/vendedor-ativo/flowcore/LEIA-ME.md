# Patch 2 para o patch FlowCore v2_3 — só testes (15/10/2026)

`patch2-testes-sqlite-e-migration.patch` (sha256 `1e80e3de…0515a`) altera **apenas dois arquivos de teste**; nenhum código de produção do patch FlowCore muda.

**Ordem de aplicação (sempre numa cópia, nunca direto na VPS):** base confirmada (25 arquivos) → `store_sales.py` da base → patch `flowcore-integration-proposal-v2_3.patch` → este patch 2. Se a árvore tiver CRLF (cópia portátil do Windows) use `git apply --ignore-whitespace`.

## O que corrige
1. **`tests/test_store_migration.py` (regressão reproduzida):** o teste da migration antiga `f4c18a2d9e10` comparava as colunas com o modelo atual, que agora tem `integration_source` (criada só pela `a84d20b1c6f3`). Agora descarta explicitamente essa coluna posterior. Teste novo cobre a `a84d20b1c6f3`: `down_revision == 9e2f1c6d7a80`, upgrade (coluna, índice e tabela `integration_idempotency`) e downgrade.
2. **`tests/test_flowcore_integration.py` (2 falhas no SQLite antigo):** nova fixture `strict_sqlite` (BEGIN explícito antes do 1º SAVEPOINT, receita do SQLAlchemy para pysqlite, só no engine do teste). `test_savepoint_failure_does_not_leave_receipt` e `test_quote_does_not_debit_and_confirmation_rejects_changed_price` passam a rodar em transação real. O teste original em modo antigo ficou como **`xfail(strict=True)` documentando a limitação conhecida** (o SAVEPOINT é liberado fora de transação e o recibo fica gravado); se o comportamento mudar, ele acusa.

## Resultado (autor, sandbox, dados sintéticos)
- Base limpa + patch 2: **15 passam, 1 xfail esperado** (antes: 11 passam, 2 falham, no mesmo conjunto).
- Mutação: trocar `rollback` por `commit` na rejeição da criação de orçamento → 2 testes falham (o novo de SAVEPOINT e o de comparação).
- O código de produção não mudou, então o resultado do harness de PostgreSQL (6/6, ver `REVISAO_PATCH_FLOWCORE_20261015.md`) continua valendo; ele não foi reexecutado com este patch.

## O que isto NÃO resolve
Catálogo sem paginação e com produtos inativos; segredo único estático; criação de contato/cliente para telefone novo; evidência em produção. "Testado pelo autor" não significa funcionando em produção.
