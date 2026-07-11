# Project Status — Dario OS

## Resumo executivo

| | |
|---|---|
| **Versão atual** | v1.2.0 |
| **Última release** | v1.2.0 — 2026-07-11 (`174569a`) |
| **Status geral** | ✅ Em produção, sem bloqueadores conhecidos |
| **Endpoints HTTP** | 59 (todos os routers, incluindo os 12 admin) |
| **Agents** | 5 (`personal`, `church`, `store`, `content`, `assistant`) |
| **Tools** | 36 |
| **Providers plugáveis** | 13, em 6 categorias (WhatsApp: 4, LLM: 5, Mail: 1, Calendar: 1, Contacts: 1, Drive: 1) |
| **Páginas frontend** | 23 (10 app principal, 12 admin, 1 login) |
| **Testes** | 555 backend + 108 frontend (unit) + 23 E2E (Playwright) = **686** |
| **Cobertura** | 94% backend; ~95% em `components/admin`, `lib` e `hooks` no frontend |

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
| Deploy | Docker Compose (8 serviços) |

## Domínios funcionais

- **WhatsApp** ponta a ponta (webhook → job → pipeline → agente → resposta → envio), 4 gateways plugáveis.
- **Google Workspace**: Gmail (leitura), Calendar (leitura/escrita), Contacts (leitura/escrita), Drive (base de conhecimento).
- **Agenda/tarefas/notas internas**, **Igreja**, **Loja** — domínios CRUD próprios do Dario OS.
- **Memória permanente**: curto prazo, longo prazo (Qdrant), conhecimento, preferências, resumo por contato.
- **Dashboard Administrativo** (`/admin`, `role=admin`): observabilidade completa do sistema.

## Timeline de versões

Ver `VERSION_HISTORY.md` para a linha do tempo completa.

- v1.0.0 (2026-07-10) — arquitetura inicial
- v1.1.1 (2026-07-10) — Google Workspace (Gmail, Calendar, Contacts, Drive)
- v1.1.2 (2026-07-10) — correção das migrations PostgreSQL ENUM
- v1.2.0 (2026-07-11) — Dashboard Administrativo, Observabilidade, Playwright, OpenTelemetry, Production Hardening

## Estado da validação (v1.2.0)

| Validação | Resultado |
|---|---|
| TypeScript | ✅ 0 erros |
| ESLint | ✅ 0 erros/warnings |
| Ruff | ✅ All checks passed |
| Pytest | ✅ 555 passed |
| Frontend tests (Vitest) | ✅ 108 passed |
| Playwright (E2E) | ✅ 23 passed |
| Build de produção (Next.js) | ✅ sucesso |
| `alembic check` (drift) | ✅ nenhuma operação pendente |
| `docker compose config` | ✅ válido |
| `docker compose up` (real) | ⚠️ não executável neste tipo de ambiente de sandbox — ver `OPERATIONS_RUNBOOK.md` |
| Google OAuth (round-trip real) | ⚠️ validado só por código/testes — ver `KNOWN_LIMITATIONS.md` |

## Pendências conhecidas

Ver `KNOWN_LIMITATIONS.md` (limitações reais de comportamento) e
`TECHNICAL_DEBT.md` (débito técnico interno). Nenhuma pendência listada é
um bloqueador de produção — todas são gaps documentados e aceitos por
decisão de escopo, endereçáveis em versões futuras (`ROADMAP_v2.md`).

## Como contribuir

Ver `CONTRIBUTING.md`.
