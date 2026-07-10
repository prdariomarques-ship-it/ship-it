# Dario OS v1.0

**Status**: Released
**Data**: 10/07/2026
**Tag**: `v1.0.0`
**Commit**: `1f59b70` (correção de PROD-004/PROD-005 — o estado exato aprovado para produção)
**Branch**: `master`

## Registro

A versão 1.0 do Dario OS foi concluída, auditada e aprovada para produção.

| Marco | Referência |
| --- | --- |
| Decisão final da auditoria | `PRODUCTION_APPROVAL.md` — **STATUS: APROVADO PARA PRODUÇÃO** |
| Bloqueadores encontrados e corrigidos | `PRODUCTION_BLOCKERS_RESOLVED.md` — PROD-004 e PROD-005, ambos **CORRIGIDO** |
| O que está incluído nesta versão | `RELEASE_NOTES_v1.0.md`, `CHANGELOG.md` |
| Propósito e princípios do produto | `VISION.md` |
| Preparação para operação contínua | `POST_RELEASE_REVIEW.md` e a documentação operacional (`OPERATIONS.md`, `BACKUP.md`, `RESTORE.md`, `MONITORING.md`, `INCIDENT_RESPONSE.md`, `RUNBOOK.md`, `MAINTENANCE_PLAN.md`) |
| Backlog priorizado da próxima versão | `ROADMAP_v1.1.md` |

## Verificação no momento do release

- 246 testes automatizados passando, lint limpo, sem drift de schema nas migrações.
- `docker compose config` validado.
- Nenhum bloqueador de segurança em aberto.

## Nota sobre a tag Git

A tag `v1.0.0` foi criada localmente apontando para o commit `1f59b70`, mas o push da tag para `origin` foi bloqueado por uma restrição de permissão (HTTP 403) neste ambiente de sessão — branches são aceitos, tags não. A tag ainda precisa ser publicada manualmente (`git push origin v1.0.0`, ou criada diretamente pela interface do GitHub apontando para `1f59b70`) para que o release fique publicamente marcado no repositório remoto.
