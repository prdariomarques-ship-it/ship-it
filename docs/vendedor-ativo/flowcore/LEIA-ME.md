# Patches 2 e 3 para o patch FlowCore v2_3 (15/10/2026)

Ordem de aplicação, **sempre numa cópia, nunca direto na VPS**: base confirmada (25 arquivos) → `store_sales.py` da base (mantém `synchronize_session=False`) → `flowcore-integration-proposal-v2_3.patch` → patch 2 → patch 3. Árvore com CRLF (cópia portátil): `git apply --ignore-whitespace`. Identificação por hash e logs: `HASHES_E_LOGS_20261015.md`.

- **Patch 2** (`patch2-testes-sqlite-e-migration.patch`): só testes. Era uma aproximação do PostgreSQL no SQLite (BEGIN explícito) e deixava um `xfail` amplo; **não corrigia o comportamento do código** e não deve ser chamado de correção do SQLite legado.
- **Patch 3** (`patch3-claim-on-conflict-e-migration-completa.patch`): **muda código de produção** (`api/integrations_flowcore.py::_claim_key`) e responde à revisão do patch 2:
  1. O claim de idempotência usa `INSERT … ON CONFLICT DO NOTHING RETURNING id` (sem SAVEPOINT) em PostgreSQL e SQLite. No PostgreSQL, uma inserção concorrente não confirmada faz o INSERT esperar a outra transação; confirmada → conflito reconhecido, desfeita → procede.
  2. O `xfail` acabou: o teste do modo antigo passa de verdade. Provas de "tudo ou nada": recibo, contato novo, cliente e orçamento somem **juntos** quando a requisição falha depois deles (SQLite estrito, SQLite antigo e PostgreSQL), e o retry com a mesma chave funciona.
  3. PostgreSQL: resposta perdida (mesma chave repetida devolve o mesmo resultado, sem novo orçamento nem nova baixa, para criação e confirmação) e chave reutilizada com outro corpo (409, nada criado).
  4. Migration: `tests/test_store_migration.py` compara o esquema histórico **escrito à mão** (separado do modelo atual); `tests/flowcore_postgres_migration_harness.py` roda `alembic upgrade head` a partir de um banco vazio, confere cabeça única, esquema histórico, preservação das linhas no upgrade e no downgrade, e reupgrade. Nenhuma migration antiga foi alterada.

## Limites
- Catálogo completo com inativos e segredo dedicado fazem parte do contrato original; paginação, rotação e permissões por loja são melhorias separadas e **não** foram feitas.
- A criação de contato ainda usa SAVEPOINT (provado desfeito junto no rollback). Outros bancos além de PostgreSQL e SQLite usam o caminho antigo do claim.
- "Testado pelo autor" não significa funcionando em produção; nada foi instalado na VPS.
