# Project Status — Dario OS

**⚠️ Esta página estava desatualizada desde a v1.2.0 (07-11) apesar de se apresentar como o snapshot atual — atualizada em 2026-07-15 só nos números efetivamente reconferidos nesta data (ver marcações abaixo). Endpoints/Agents/Tools/Providers/Páginas/Cobertura não foram reconferidos agora e podem estar desatualizados.**

## Resumo executivo

| | |
|---|---|
| **Última verificação** | 2026-07-15 |
| **Status geral** | ✅ Em produção, sem bloqueadores conhecidos |
| **Endpoints HTTP** | 59 *(não reconferido em 07-15)* |
| **Agents** | 5 (`personal`, `church`, `store`, `content`, `assistant`) *(não reconferido em 07-15)* |
| **Tools** | 36 *(não reconferido em 07-15)* |
| **Providers plugáveis** | 13, em 6 categorias (WhatsApp: 4, LLM: 5, Mail: 1, Calendar: 1, Contacts: 1, Drive: 1) *(não reconferido em 07-15)* |
| **Páginas frontend** | 23 (10 app principal, 12 admin, 1 login) *(não reconferido em 07-15)* |
| **Testes** | 758 backend + 108 frontend (unit) — reconferido em 07-15, rodando 2x em host + 1x em container, todos passando |
| **Serviços Docker** | 12 (postgres, redis, qdrant, backend, frontend, caddy, n8n, openwa, jaeger, prometheus, alertmanager, grafana) — reconferido em 07-15 |
| **Cobertura** | 94% backend; ~95% em `components/admin`, `lib` e `hooks` no frontend *(não reconferido em 07-15)* |

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

## Estado da validação (última verificação 2026-07-15)

| Validação | Resultado |
|---|---|
| TypeScript (via `next build`) | ✅ 0 erros |
| ESLint | ✅ 0 erros/warnings |
| Ruff (lint) | ✅ All checks passed |
| mypy | ✅ 0 erros (263 arquivos) |
| Pytest | ✅ 758 passed (host); 753/758 em container — as 5 restantes são artefato do filesystem restrito do container (ver TECHNICAL_DEBT.md), confirmadas passando no ambiente equivalente ao CI real |
| Frontend tests (Vitest) | ✅ 108 passed |
| Playwright (E2E) | *(não reexecutado em 07-15)* |
| Build de produção (Next.js) | ✅ sucesso |
| `alembic upgrade head` (do zero) | ✅ 11 migrations aplicadas, schema consistente |
| `docker compose config` | ✅ válido |
| `docker compose up` (real) | ✅ executado — stack de 12 serviços saudável |
| Google OAuth (round-trip real) | ⚠️ validado só por código/testes — ver `KNOWN_LIMITATIONS.md` |
| WhatsApp (OpenWA) | ⚠️ crash loop corrigido, mas sessão exige novo QR code (aguardando ação humana) e há incompatibilidade não resolvida com o WhatsApp Web atual — ver `TECHNICAL_DEBT.md` |

## Pendências conhecidas

Ver `KNOWN_LIMITATIONS.md` (limitações reais de comportamento) e
`TECHNICAL_DEBT.md` (débito técnico interno). Nenhuma pendência listada é
um bloqueador de produção — todas são gaps documentados e aceitos por
decisão de escopo, endereçáveis em versões futuras (`ROADMAP_v2.md`).

## Como contribuir

Ver `CONTRIBUTING.md`.
