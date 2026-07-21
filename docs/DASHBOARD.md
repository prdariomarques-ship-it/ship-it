# Dashboard Administrativo — Sprint 4

Painel administrativo somente leitura para o Dario OS, no estilo de produtos como
LangSmith, Grafana, Datadog e OpenAI Platform: status dos sistemas, agentes e
tools registrados, timeline de execuções, memória (Qdrant/embeddings), Google
Workspace, WhatsApp, usuários, logs, métricas e informações de sistema.

**Escopo desta sprint**: exclusivamente aditivo. Nenhuma regra de negócio, nenhum
comportamento do Orchestrator/Event Bus/Memory Manager/Agents/Providers/OAuth foi
alterado — apenas um novo namespace de leitura (`/api/admin/*`) e um novo painel
Next.js consumindo dados que já existiam. Ver `DASHBOARD_REPORT.md` para a lista
completa de arquivos criados/alterados e o resultado de todas as validações.

## Acesso

`https://<seu-domínio>/admin` (ou `http://localhost:3000/admin` em dev). Exclusivo
para usuários com `role = admin`:

- **Backend**: todo endpoint `/api/admin/*` tem `dependencies=[Depends(require_admin)]`
  — um usuário não-admin recebe `403` mesmo com um token válido.
- **Frontend**: `hooks/use-admin-guard.ts` consulta `GET /auth/me` (endpoint já
  existente) e bloqueia a UI (tela "Acesso restrito") para quem não for admin —
  isso evita mostrar a interface administrativa e só então levar uma sequência de
  403 em cada card; a garantia real de autorização é sempre a do backend.

Nunca são retornados pelo backend: `encrypted_refresh_token`, `hashed_password`,
qualquer `*_api_key`/`*_secret`/`access_token`/JWT. Verificado por teste
(`backend/tests/test_admin.py`) em cada endpoint que toca uma tabela com esses
campos.

## Arquitetura

- **Backend**: `backend/admin/` — `schemas.py` (modelos de resposta Pydantic),
  `service.py` (helpers só-leitura: git info, psutil, snapshot do Prometheus,
  probes de componentes), `router.py` (12 rotas, prefixo `/admin`, registrado em
  `main.py` como qualquer outro router — nenhuma rota existente foi tocada).
- **Frontend**: `frontend/app/admin/` — um grupo de rotas **fora** de
  `app/(dashboard)/` (não empilha com o layout/sidebar do app principal),
  layout próprio (`app/admin/layout.tsx` → `AdminShell`), tema escuro isolado
  (`styles/admin.css`, classe `.admin-theme`, Tailwind com `preflight`
  desabilitado para nunca afetar visualmente as páginas existentes).
- **Design system**: Tailwind + componentes no padrão shadcn/ui (código copiado e
  adaptado, não uma dependência de pacote — é assim que shadcn/ui funciona por
  design) em `components/admin/ui/`, gráficos com Recharts, ícones Lucide,
  transições com Framer Motion, dados via TanStack React Query.

## Dados: exatamente o que já existia

Nenhum novo mecanismo de coleta de dados foi criado. Cada endpoint lê de uma
fonte que já existia antes desta sprint:

| Endpoint | Fonte real dos dados |
|---|---|
| `GET /api/admin` | `Agent Registry`, `Tool Registry`, tabelas `users`/contas Google, `WhatsAppProvider.health_check()` |
| `GET /api/admin/status` | `SELECT 1` (DB), ping Redis, `Qdrant.get_collections()`, `WhatsAppProvider.health_check()`, introspecção do `EventBus` em memória, `GOOGLE_CLIENT_ID/SECRET` configurados |
| `GET /api/admin/system` | `git rev-parse`/`describe` (melhor esforço), `psutil` (CPU/RAM/disco), `engine.pool`, `Settings` (nomes de provider, nunca segredos) |
| `GET /api/admin/agents` | `agents.registry.list_agents()` + snapshot do registro Prometheus (`observability/metrics.py`) + `LogEntry` mais recente com `source="agent:<nome>"` |
| `GET /api/admin/tools` | `agents.tools.registry.list_tools()` + mesmo snapshot Prometheus |
| `GET /api/admin/logs` | Tabela `logs` (`LogEntry`) |
| `GET /api/admin/google` | Tabelas `email_accounts`, `google_calendar_accounts`, `google_contacts_accounts`, `google_drive_accounts`, `google_drive_indexed_files` |
| `GET /api/admin/memory` | `MemoryService.client.get_collection()` (Qdrant), tabela `embeddings`, tabela `google_drive_indexed_files`, `CacheService._redis_available` |
| `GET /api/admin/executions` | Tabelas `jobs` e `logs` (`source LIKE 'agent:%'`) — ver limitação abaixo |
| `GET /api/admin/users` | Tabela `users` (sem `hashed_password`) |
| `GET /api/admin/metrics` | Snapshot bruto do registro Prometheus já usado por `GET /metrics` |
| `GET /api/admin/whatsapp` | `WhatsAppProvider.health_check()`, tabela `jobs` (fila), tabela `messages` (contagem por direção), `OPENWA_PUBLIC_QR_URL` (só quando `WHATSAPP_PROVIDER=openwa`, senão `qr_page_url: null`) |

## Limitações conhecidas (decisões explícitas, não lacunas esquecidas)

Duas decisões de escopo foram tomadas explicitamente com o solicitante antes da
implementação, para não violar a proibição de alterar
Orchestrator/Agents/Providers:

1. **Não existe tabela de auditoria de execuções por agente/tool.** Não há, hoje,
   nenhum registro histórico e consultável de "agente X rodou a tool Y às HH:MM,
   levou Zs, gastou N tokens, para o usuário W". O que existe:
   - Contadores **cumulativos** do Prometheus (`darioos_agent_runs_total`,
     `darioos_agent_tool_calls_total`, `darioos_agent_run_duration_seconds`) —
     resetam a cada restart do processo, sem granularidade por execução
     individual.
   - A tabela `jobs` (trabalho em background genérico) e a tabela `logs` (quando
     um evento específico foi logado com `source="agent:*"`).

   Por isso: **Agents** e **Tools** mostram `runs_total`/`calls_total`/
   `avg_duration_seconds` a partir do Prometheus (quando disponível) e marcam
   como `null` (exibido como "não disponível" na UI, nunca um `0` fabricado)
   os campos sem fonte real — `permissions` (não modelado em `Tool`) e
   `last_call` por tool (nenhum registro traz timestamp por chamada). A página
   **Executions** é uma timeline honesta construída sobre `jobs` + `logs`, não
   uma auditoria completa: não há filtro por Tool (nenhum registro liga uma
   linha de log/job a uma tool específica), e `tokens`/`usuário` por execução
   não existem.

2. **QR Code do WhatsApp (só openwa).** `GET /admin/whatsapp` retorna
   `qr_page_url` — um link para a página de pareamento própria do gateway
   openwa (servida por ele mesmo na porta 8002), nunca um proxy/embed do QR
   em si. Só populado quando `WHATSAPP_PROVIDER=openwa` **e**
   `OPENWA_PUBLIC_QR_URL` está configurada (`docker/.env.example` documenta
   formato e um exemplo de reverse proxy via Caddy); ausente/`null` em
   qualquer outro caso, e a página **WhatsApp** esconde a seção
   correspondente sem mostrar link quebrado. Motivo de não ter um proxy REST
   embutido: confirmado ao vivo contra o gateway rodando que não existe
   método `getQRCode` (nem equivalente) na API REST args-based do
   wa-automate — o QR só é entregue via WebSocket para a página popup do
   próprio gateway, então o dashboard aponta para ela em vez de tentar
   replicá-la.

Limitações adicionais, menores:

- **Última sincronização** só existe de verdade para o Google Drive
  (`google_drive_indexed_files.indexed_at`) — Gmail/Calendar/Contacts são
  domínios *read-through* (consultam a API do Google a cada chamada, não
  indexam), então não há um "último sync" para mostrar; o card exibe "não
  disponível" em vez de inventar uma data.
- **Gráficos "em tempo real"** (Executions/min, Tokens/min, Erros/min, Latência,
  CPU, Memória, Disco) são construídos por **polling** (a cada 5s para
  status/metrics/whatsapp, 30s para o resto) — não há WebSocket nem série
  temporal persistida no backend. O frontend acumula uma janela local de
  amostras (`hooks/use-rolling-series.ts`) e, para os contadores cumulativos do
  Prometheus, calcula uma taxa por minuto comparando duas leituras sucessivas
  (`useRatePerMinute`). Um gráfico mostra "Coletando dados…" até ter pelo menos
  duas leituras — não é um placeholder quebrado, é o estado esperado logo após
  abrir a página.
- **`/admin/memory`**: se o Qdrant não estiver acessível ou a coleção ainda não
  existir, `points_count`/`vectors_count` voltam `null` ("não disponível") em
  vez de lançar erro — a contagem de embeddings/chunks por origem (Postgres)
  continua funcionando normalmente, já que não depende do Qdrant.

## Segurança

- Todo endpoint admin exige `role=admin` (backend) e é bloqueado também no
  cliente antes de renderizar (evita expor a UI, não é o mecanismo de
  autorização real).
- Nenhum campo de token/segredo é serializado em nenhuma resposta — coberto por
  teste (`test_admin_google_never_leaks_the_encrypted_refresh_token`,
  `test_admin_users_never_leaks_password_hash`,
  `test_admin_system_exposes_provider_names_but_never_secrets`).
- O botão **Reconnect** (página Google Workspace) chama o endpoint `/connect`
  que cada domínio Google já expunha antes desta sprint
  (`/api/mail/connect`, `/api/gcalendar/connect`, etc.) — nenhuma lógica OAuth
  nova, apenas um link para o fluxo existente.
- A página **Settings** é somente leitura (spec desta sprint): mostra nomes de
  provider (`openai`, `openwa`, ...) e flags de comportamento
  (`auto_reply_enabled`, `jobs_enabled`), nunca chaves de API — editar
  configuração continua sendo feito via `.env`.

## Componentes reutilizáveis

`components/admin/`: `StatusCard`, `MetricCard`, `AgentCard`, `ToolTable`,
`ExecutionTimeline`, `SystemHealth`, `MemoryStatsView`, `GoogleCard`,
`LogViewer`, `charts/MetricChart`, além de `EmptyState`/`ErrorState`/
`LoadingGrid` (skeleton) para os três estados de UX pedidos em todas as
páginas, e `PageHeader`, `AdminSidebar`, `AdminHeader`, `AdminShell`
(orquestra guarda de acesso + providers).

## Testes

- **Backend** (`backend/tests/test_admin.py`): 61 testes — 401/403/200 em cada
  um dos 12 endpoints, formato de resposta, filtros (logs, executions), e
  testes específicos de "nunca vaza segredo". Dois testes de regressão
  (`test_admin_agents_reflects_real_prometheus_counters_end_to_end`,
  `test_admin_tools_reflects_real_prometheus_counters_end_to_end`) cobrem um
  bug real encontrado durante o desenvolvimento (ver `DASHBOARD_REPORT.md`).
- **Frontend** (`frontend/tests/`, Vitest + React Testing Library): 106 testes
  cobrindo os 10 componentes nomeados na spec, os hooks (`use-rolling-series`,
  `use-admin-guard`, `use-portal-container`, `use-toast`), os helpers
  (`lib/format.ts`, `lib/metrics-helpers.ts`) e todos os 12 hooks de
  `lib/admin-api.ts`. Rode com `npm test` (ou `npm run test:coverage`).
- **Smoke test manual em navegador real** (Playwright + Chromium, contra
  backend/Postgres/Redis reais, dados semeados): login, guarda de
  acesso (admin e não-admin), as 12 páginas, e interações (abrir/fechar o
  modal de detalhe de uma tool, abrir o seletor de período em Executions).
  Encontrou e corrigiu dois bugs visuais reais que nenhuma outra checagem
  (TypeScript, ESLint, build) detectaria — ver `DASHBOARD_REPORT.md`.

## Como rodar localmente

```bash
# Backend
cd backend && uvicorn main:app --reload

# Frontend
cd frontend && npm run dev
# abrir http://localhost:3000/admin (usuário precisa ter role=admin)
```
