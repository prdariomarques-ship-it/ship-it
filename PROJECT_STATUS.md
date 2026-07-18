# Project Status — Dario OS

**⚠️ Esta página estava desatualizada desde a v1.2.0 (07-11) apesar de se apresentar como o snapshot atual. Atualizada em 2026-07-17 (RC1 audit, ver `RC1_AUDIT.md`) nos números efetivamente reconferidos nesta data (ver marcações abaixo); Endpoints, Agents, Tools, Providers e Cobertura não foram reconferidos nesta passagem e podem estar desatualizados — a reconferência de 07-16 desses campos específicos ainda vale como última verificação real. Atualizada de novo em 2026-07-18 (GA de v1.3.0 + patch v1.3.1) só nos campos de teste/versão — ver nota abaixo.**

## Resumo executivo

| | |
|---|---|
| **Última verificação** | 2026-07-18 (testes e timeline de versão); 2026-07-17 (páginas); 2026-07-16 (demais campos) |
| **Status geral** | ✅ Em produção, sem bloqueadores conhecidos. **v1.3.0 GA e v1.3.1 (patch) tagueadas** — ver `RC1_AUDIT.md` e `RELEASE_READINESS.md` |
| **Endpoints HTTP** | 85 rotas distintas (`/openapi.json`) — reconferido em 07-16, +1 rota nova em 07-17 (`POST /admin/actions/log`, ver `ACTION_CENTER.md`) não recontada no total; -1 rota em 07-18 (`POST /api/jobs/{id}/cancel` removida por duplicidade, ver `RELEASE_READINESS.md`), também não recontada |
| **Agents** | 5 (`personal`, `church`, `store`, `content`, `assistant`) — reconferido em 07-16 |
| **Tools** | 40 — reconferido em 07-16 |
| **Providers plugáveis** | 13, em 6 categorias (WhatsApp: 4, LLM: 5, Mail: 1, Calendar: 1, Contacts: 1, Drive: 1) *(não reconferido em 07-16)* |
| **Páginas frontend** | 27 (11 app principal, 15 admin, 1 login) — reconferido em 07-17 via `next build` (+3 admin desde 07-16: Timeline, Briefing Diário, Central de Ações — ver `MEMORY_TIMELINE.md`, `DAILY_BRIEFING.md`, `ACTION_CENTER.md`) |
| **Testes** | 864 backend + 240 frontend (unit) — backend reconferido em 07-18 (v1.3.1, todos passando; caiu de 886→864 pela remoção de 21 testes de código morto, não regressão — ver `RELEASE_READINESS.md`); frontend não tocado nem rerodado em 07-18, número herdado de 07-17 |
| **Serviços Docker** | 12 (postgres, redis, qdrant, backend, frontend, caddy, n8n, openwa, jaeger, prometheus, alertmanager, grafana) — reconferido em 07-16 |
| **Cobertura** | 94% backend; ~95% em `components/admin`, `lib` e `hooks` no frontend *(não reconferido em 07-16 nem 07-17 nem 07-18)* |

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2 |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind (admin), React Query, Recharts |
| Banco | PostgreSQL |
| Cache / filas / rate limit | Redis (com fallback em memória) |
| Memória semântica | Qdrant |
| Reverse proxy | Caddy (HTTPS automático) |
| Automação externa opcional | n8n |
| Autenticação | JWT + refresh token rotativo, RBAC (`admin`/`user`) |
| Observabilidade | Logs JSON estruturados, Prometheus, health/readiness, Correlation ID, OpenTelemetry (opcional) |
| Testes | Pytest + pytest-asyncio (backend); Vitest + Testing Library (frontend); Playwright + axe-core (E2E) |
| Deploy | Docker Compose (12 serviços) |

## Domínios funcionais

- **WhatsApp** ponta a ponta (webhook → job → pipeline → agente → resposta → envio), 4 gateways plugáveis.
- **Google Workspace**: Gmail (leitura), Calendar (leitura/escrita), Contacts (leitura/escrita), Drive (base de conhecimento).
- **Agenda/tarefas/notas internas**, **Metas** (`GoalManager`: prazo, dependências, recorrência, aprovação), **Igreja**, **Loja** — domínios CRUD próprios do Dario OS.
- **Memória permanente**: curto prazo, longo prazo (Qdrant), conhecimento, preferências, resumo por contato.
- **Dashboard Administrativo** (`/admin`, `role=admin`): observabilidade completa do sistema.

## Timeline de versões

Ver `VERSION_HISTORY.md` para a linha do tempo completa.

- v1.0.0 (2026-07-10) — arquitetura inicial
- v1.1.1 (2026-07-10) — Google Workspace (Gmail, Calendar, Contacts, Drive)
- v1.1.2 (2026-07-10) — correção das migrations PostgreSQL ENUM
- v1.2.0 (2026-07-11) — Dashboard Administrativo, Observabilidade, Playwright, OpenTelemetry, Production Hardening
- v1.3.0-rc1 (2026-07-17) — AI Operator Center, Memory & Timeline, Daily Briefing, Action Center. Ver `RC1_AUDIT.md`.
- v1.3.0 (2026-07-18, tag em `d64b8be`) — GA da mesma leva do RC1, já com o fix crítico do sidebar mobile incluído.
- v1.3.1 (2026-07-18) — patch: resolve os dois achados Medium do `RC1_AUDIT.md` (funções mortas em `validation.py`; endpoint duplicado em `jobs/router.py`). Ver `RELEASE_READINESS.md`.

## Estado da validação (última verificação 2026-07-18, v1.3.1)

| Validação | Resultado |
|---|---|
| TypeScript (via `next build`) | ✅ 0 erros *(última execução real: 07-17, não rerodado em 07-18 — frontend não tocado)* |
| ESLint | ✅ 0 erros/warnings *(última execução real: 07-17)* |
| Ruff (lint + format) | ✅ All checks passed nos arquivos tocados em 07-18; formatação geral não rerodada desde 07-16 |
| mypy | ✅ 0 erros (275 arquivos) *(última execução real: 07-16, não rerodado em 07-17/07-18)* |
| Pytest | ✅ 864 passed (host, caminho real do repo) — reconferido em 07-18 |
| Frontend tests (Vitest) | ✅ 240 passed *(última execução real: 07-17, não rerodado em 07-18 — frontend não tocado)* |
| Playwright (E2E) | *(não reexecutado em 07-16)* |
| Build de produção (Next.js) | ✅ sucesso |
| `alembic upgrade head` (do zero) | ✅ 12 migrations aplicadas, schema consistente |
| `docker compose config` | ✅ válido |
| `docker compose up` (real) | ✅ executado — stack de 12 serviços saudável, rebuild+redeploy de `backend`/`frontend`/`openwa` validados ao vivo repetidas vezes |
| Google OAuth (round-trip real) | ⚠️ validado só por código/testes — ver `KNOWN_LIMITATIONS.md` |
| WhatsApp (OpenWA) | ✅ estável em produção — sessão conectada, `sendText` validado; `sendImage`/`sendFile`/`sendButtons` seguem indisponíveis (gap do próprio open-wa) — ver `TECHNICAL_DEBT.md` |

## Pendências conhecidas

Ver `KNOWN_LIMITATIONS.md` (limitações reais de comportamento) e
`TECHNICAL_DEBT.md` (débito técnico interno). Nenhuma pendência listada é
um bloqueador de produção — todas são gaps documentados e aceitos por
decisão de escopo, endereçáveis em versões futuras (`ROADMAP_v2.md`).

Ver também `RC1_AUDIT.md` (2026-07-17) para os achados específicos do
ciclo AI Operator Center / Memory & Timeline / Daily Briefing / Action
Center. O achado crítico (sidebar do admin sem responsividade mobile) foi
corrigido e deployado em 2026-07-18; os dois achados Medium que exigiam
decisão de produto (funções mortas em `validation.py`; endpoint duplicado
em `jobs/router.py`) foram resolvidos e deployados no mesmo dia como
v1.3.1 — ver `RELEASE_READINESS.md` e `CURRENT_PROJECT_STATE.md`.

## Como contribuir

Ver `CONTRIBUTING.md`.
