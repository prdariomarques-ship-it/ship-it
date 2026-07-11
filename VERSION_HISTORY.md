# Version History — Dario OS

Linha do tempo completa do projeto. Cada versão aponta para a tag Git
correspondente e, quando existe, o relatório técnico da fase/sprint. Para o
detalhamento completo de cada release, ver `CHANGELOG.md`.

----------------------------------------

## v1.0.0 — 2026-07-10

**Arquitetura inicial**

Primeira versão do Dario OS. Backend FastAPI + SQLAlchemy 2 async, dashboard
Next.js 14, Docker Compose completo (Postgres, Redis, Qdrant, n8n, Caddy).
5 agentes de IA, 4 Providers de WhatsApp, 5 Providers de LLM, Agent/Tool
Registry com auto-descoberta, Event Bus, AI Orchestrator, Memory Manager,
Cognitive Pipeline (Intent/Priority Engine, Planner, Response Validator,
Learning Engine), fila de jobs durável. 246 testes, 92% de cobertura.

Aprovado para produção — ver `PRODUCTION_APPROVAL.md`,
`PRODUCTION_BLOCKERS_RESOLVED.md`, `RELEASE_NOTES_v1.0.md`.

----------------------------------------

## v1.1.1 — 2026-07-10

**Google Workspace**

Quatro domínios novos e isolados, cada um com OAuth próprio, acessíveis
apenas pelo agente `assistant` (gateway único):

- Sprint 1: **Gmail** (leitura, busca, resumo, detecção de pendências).
- Sprint 2: **Google Calendar** e **Google Contacts** (leitura e escrita).
- Sprint 3: **Google Drive** como base de conhecimento (indexação alimenta o
  Memory Manager/Qdrant já existente).

Correções de auditoria antes do code freeze: XSS refletido e corrida de
conexão no Gmail (Sprint 1.1), vetores órfãos e path traversal na
plataforma Google (auditoria final).

Aprovado para produção — ver `GOOGLE_PLATFORM_AUDIT.md`,
`SPRINT_1_1_VALIDATION.md`.

(Não existe tag `v1.1.0` — a numeração pulou direto para `v1.1.1`, que já
inclui a consolidação de tudo acima.)

----------------------------------------

## v1.1.2 — 2026-07-10

**Correção definitiva das migrations PostgreSQL ENUM**

`CREATE TYPE` implícito do SQLAlchemy/asyncpg só é emitido pela primeira
migration que referencia cada `ENUM` — uma migration posterior que
reutilizasse o mesmo tipo falhava com `UndefinedObjectError` em qualquer
banco que ainda não tivesse a revisão original aplicada. Migrations
passaram a criar os tipos `ENUM` do Postgres explicitamente.

Ver `MIGRATION_FIX_REPORT.md` para a evidência completa (causa raiz, diff,
validação em banco novo/parcial, upgrade/downgrade).

----------------------------------------

## v1.2.0 — 2026-07-11

**Dashboard Administrativo, Observabilidade, Playwright, OpenTelemetry,
Production Hardening**

- **Sprint 4 — Dashboard Administrativo**: painel somente leitura em
  `/admin` (12 rotas `/api/admin/*`, `role=admin`), construído inteiramente
  sobre dados que já existiam. Ver `docs/DASHBOARD.md`, `DASHBOARD_REPORT.md`.
- **Sprint 5 — Production Hardening**: sem novas funcionalidades de
  usuário. Correlation/Request ID, tracing OpenTelemetry opcional, suíte
  E2E com Playwright (23 testes), auditoria de segurança/performance/
  observabilidade. Dois bugs reais de produção encontrados e corrigidos
  (busca semântica de memória quebrada pelo `qdrant-client` 1.18+; erro de
  login não exibido na UI). Ver `SPRINT5_REPORT.md`,
  `PRODUCTION_READINESS.md`, `SECURITY_AUDIT.md`, `PERFORMANCE_REPORT.md`,
  `OBSERVABILITY_GUIDE.md`.

555 testes de backend (94% de cobertura), 108 testes de frontend, 23
testes E2E.

----------------------------------------

## Convenção de versionamento

O projeto segue [SemVer](https://semver.org/lang/pt-BR/) informalmente:
incrementos de `MINOR` acompanham a entrega de uma sprint com escopo
funcional novo (Google Workspace, Dashboard); incrementos de `PATCH`
são correções pontuais sem funcionalidade nova (migrations, bugs). Não
houve, até aqui, nenhuma mudança que justificasse um incremento de
`MAJOR` — nenhuma API pública ou contrato de dados foi quebrado entre
versões.

Para o que vem a seguir, ver `ROADMAP_v2.md`.
