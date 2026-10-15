# Revisão do pacote do revisor (flowcore-review-package-20261015)

Data: 2026-10-15. Nada foi aplicado na VPS nem no código de produção; só leitura, reconstrução e testes.

## O que foi conferido
- Manifesto do pacote: 4 arquivos conferem.
- Árvore final reconstruída (snapshot + sobreposição de 25 arquivos + `git apply --ignore-whitespace` do patch cumulativo, sha256 `4eb09db52284538294e7b60dd1ac73dd2752fa8751b8dc53225242c49466b932`): 391 de 393 arquivos idênticos ao `final-manifest.sha256`. Os 2 que diferem (`backend/main.py`, `backend/models/__init__.py`) ficam idênticos mantendo o fim de linha original e adicionando as linhas novas em CRLF.
- O pacote declarava "testes não executados". Agora foram executados (log em `saidas/pacote_revisor_testes_20261015.txt`): SQLite 22 testes, PostgreSQL 16.13 descartável (loopback, banco `flowcore_test`) 11 testes (9 de concorrência/rollback + 2 de cadeia alembic).

## Resultado
| Execução | Resultado |
|---|---|
| Pacote como entregue | **34 passam, 1 falha** (PostgreSQL `lost_response_retry`) |
| Mesma árvore com a asserção corrigida | **35 passam** (SQLite + PostgreSQL + cadeia de migrations) |

### A falha
`tests/flowcore_postgres_harness.py:713` afirma `len(receipts) == 2` e `operations == [confirm_quote, create_quote]`. O mesmo teste faz 3 chamadas com 3 chaves diferentes (`pg-lost-create`, `pg-lost-confirm`, `pg-lost-confirm-outra-chave`), então o banco tem 3 recibos (2 de `confirm_quote`). O código está correto: uma chave nova sobre um orçamento já confirmado devolve o mesmo pedido (`duplicate=true`, estoque baixado uma vez) e registra o recibo da chave nova. O defeito é da asserção que o revisor acrescentou sem rodar. Correção: 3 recibos e `[confirm_quote, confirm_quote, create_quote]`. O pacote não deve ser aceito sem esse ajuste.

## Mutações (35 testes, árvore corrigida)
| Mutação no código | Detectada? |
|---|---|
| Remover `ON CONFLICT DO NOTHING` | Sim (5 falhas, SQLite e PostgreSQL) |
| Aceitar payload diferente com a mesma chave (sem 409) | Sim (3 falhas) |
| Remover `with_for_update` ao reler o recibo existente | **Não** |
| Dialeto desconhecido deixa de falhar fechado | **Não** |

Lacunas: (1) o `with_for_update` não é exercitado por nenhum teste, porque a corrida real exigiria dois claims simultâneos do mesmo recibo ainda não concluído; (2) o "fail closed" para dialeto fora de PostgreSQL/SQLite e a exigência de SQLite 3.35+ não têm teste. Ambas são proteções legítimas, só estão sem cobertura.

## Diferenças em relação ao meu patch3
- Mesmo núcleo: `INSERT ... ON CONFLICT DO NOTHING RETURNING id` na transação do pedido, sem SAVEPOINT.
- O pacote remove o caminho antigo com SAVEPOINT para outros bancos e falha fechado (`RuntimeError`); o patch3 mantinha esse caminho. Para um sistema que só roda em PostgreSQL e SQLite de teste, o fail-closed é a escolha mais segura, desde que ganhe um teste.
- O pacote acrescenta 4 testes SQLite de rollback e preço alterado (legacy e strict); todos passam.
- A cadeia de migrations (head único e upgrade/downgrade preservando linhas) passa no PostgreSQL.

## Recomendação
Adotar o patch cumulativo do pacote **com** (a) a asserção de recibos corrigida e (b) dois testes novos: dialeto desconhecido falha fechado, e dois claims simultâneos da mesma chave em PostgreSQL (cobrindo o `with_for_update`). Ainda não é para produção: falta decidir o segredo compartilhado `X-FlowCore-Secret` no ambiente e a revisão do FlowCore real.
