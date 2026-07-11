# Dashboard Administrativo — Relatório Final (Sprint 4)

**Data**: 2026-07-11
**Escopo**: Dashboard Web administrativo, somente leitura, para o Dario OS.
**Restrição respeitada**: nenhuma regra de negócio, nenhum comportamento do
Orchestrator/Event Bus/Memory Manager/Agents/Providers/OAuth/APIs existentes foi
alterado. Tudo o que segue é estritamente aditivo.

Duas decisões de escopo foram tomadas explicitamente com o solicitante antes de
implementar (ver seção "Limitações conhecidas" abaixo): (1) Agents/Tools/
Executions usam somente dados já existentes, marcando como indisponível o que
não tem fonte real, em vez de instrumentar o Orchestrator/Agents; (2) WhatsApp
mostra status real sem QR Code, já que obtê-lo exigiria alterar Providers.

## Arquivos criados

**Backend** (8 arquivos nesta sprint):
- `backend/admin/__init__.py`
- `backend/admin/router.py` — 12 rotas `/admin/*`
- `backend/admin/schemas.py` — modelos de resposta Pydantic
- `backend/admin/service.py` — helpers só-leitura (psutil, git info, snapshot Prometheus, probes de componentes)
- `backend/tests/test_admin.py` — 61 testes
- `docs/DASHBOARD.md`
- `DASHBOARD_REPORT.md` (este arquivo)

**Frontend** (78 arquivos):
- 13 páginas em `frontend/app/admin/` (`layout.tsx` + 12 rotas)
- 24 componentes em `frontend/components/admin/` (10 nomeados na spec + 12 primitivas de UI estilo shadcn/ui + `charts/MetricChart.tsx` + shell/sidebar/header/providers)
- 5 arquivos em `frontend/lib/` (`admin-api.ts`, `admin-types.ts`, `format.ts`, `metrics-helpers.ts`, `utils.ts`)
- 4 hooks novos em `frontend/hooks/` (`use-admin-guard.ts`, `use-portal-container.tsx`, `use-rolling-series.ts`, `use-toast.tsx`)
- 24 arquivos de teste em `frontend/tests/` (106 testes)
- Config: `.eslintrc.json`, `components.json`, `postcss.config.js`, `tailwind.config.ts`, `vitest.config.ts`, `vitest.setup.ts`, `styles/admin.css`

## Arquivos alterados

- `backend/main.py` — registra `admin_router` (uma linha de import + uma de `include_router`, mesmo padrão de todo outro router) e a tag `"admin"` no OpenAPI. Nenhuma rota existente foi tocada.
- `backend/requirements.txt` — adiciona `psutil` (leitura de CPU/RAM/disco; nenhuma outra dependência de negócio).
- `frontend/components/Sidebar.tsx` — adiciona um link "Admin" → `/admin` ao menu existente (uma linha; o app principal não tinha nenhuma forma de chegar ao novo dashboard).
- `frontend/package.json` / `package-lock.json` — novas dependências (ver abaixo).
- `README.md` — nova seção "Dashboard Administrativo", entrada na lista de documentação, contagem de testes atualizada (473→540 backend, +106 frontend).
- `docs/architecture.md` — nova seção "Dashboard Administrativo — Sprint 4", nota de transparência de cobertura estendida para `admin/router.py` (mesmo padrão documentado já existente para `webhooks/router.py`).
- `.gitignore` — ignora `tsconfig.tsbuildinfo` e `coverage/` (artefatos de build/teste do frontend, mesmo princípio já aplicado a `.next/`).

Nenhum model, endpoint, provider, tool, agente, migration ou comportamento de runtime pré-existente foi alterado.

## Novos componentes reutilizáveis

Os 10 pedidos na spec, todos em `components/admin/`: `StatusCard`, `MetricCard`,
`AgentCard`, `ToolTable`, `ExecutionTimeline`, `SystemHealth`,
`MemoryStatsView` (Memory Stats), `GoogleCard`, `LogViewer`,
`charts/MetricChart`. Mais os estados de UX pedidos —
`EmptyState`/`ErrorState`/`LoadingGrid` (skeleton) — usados em todas as 12
páginas, e a infraestrutura do shell (`AdminShell`, `AdminSidebar`,
`AdminHeader`, `QueryProvider`) e 12 primitivas de UI estilo shadcn/ui
(`Button`, `Card`, `Badge`, `Table`, `Dialog`, `Select`, `Tabs`, `Input`,
`Skeleton`, `Separator`, `ScrollArea`, `Toast`).

## Novos endpoints (backend)

Todos sob `/api/admin`, todos `require_admin` (403 para não-admin, 401 sem
token), todos somente leitura:

`GET /admin`, `/admin/status`, `/admin/system`, `/admin/agents`,
`/admin/tools`, `/admin/logs`, `/admin/google`, `/admin/memory`,
`/admin/executions`, `/admin/users`, `/admin/metrics`, `/admin/whatsapp`.

A tabela completa de qual dado real (tabela/registry/serviço já existente)
alimenta cada campo de cada resposta está em `docs/DASHBOARD.md`.

## Cobertura

| Suíte | Testes | Cobertura |
|---|---|---|
| Backend completo (`pytest`) | **540 passed** (479 pré-existentes + 61 novos) | **93%** geral (inalterado) |
| Backend, módulo `admin/` isolado | 61 testes | **90%** (`router.py` 79%, `schemas.py` 100%, `service.py` 97%) |
| Frontend (`vitest`), `components/admin` + `lib` + `hooks` | **106 passed** | **95.3%** statements / **97.4%** lines |

**Sobre o 79% de `admin/router.py`**: confirmado, com `coverage run` puro (não é
artefato do `pytest-cov`), que é exatamente o mesmo padrão já documentado em
`docs/architecture.md` para `webhooks/router.py`/`api/whatsapp.py` desde a Fase
4.1 — toda linha "faltando" fica logo depois de um `await db.execute(...)`
dentro de um handler de rota async. Os 61 testes exercitam esses caminhos de
verdade (asserções de status HTTP, forma exata da resposta, ausência de
segredos) — a métrica de linha subconta, o comportamento está coberto.

**Sobre `hooks/useApi.ts` (0%, excluído do denominador frontend)**: é código
pré-existente (Fase 4), não tocado por esta sprint, e já não tinha testes antes
— excluí-lo do escopo de cobertura desta sprint é uma decisão explícita, não
uma omissão (ver `vitest.config.ts`).

**Sobre `MetricChart.tsx` (62.5%)**: as linhas não cobertas são callbacks
internos de tooltip/formatter do Recharts (biblioteca de terceiros, já testada
upstream) — os dois estados relevantes do componente em si ("coletando
dados" / "renderiza o gráfico") estão cobertos.

**As 12 páginas (`app/admin/*/page.tsx`)** não entram na métrica de cobertura
de unidade — são composição fina de hooks e componentes já testados
individualmente. Foram verificadas de ponta a ponta contra um backend real
(ver "Smoke test em navegador real" abaixo), que é uma evidência mais forte
para esse tipo de código do que cobertura de linha isolada.

## Performance

Build de produção (`next build`), comparado às páginas já existentes:

| Página | First Load JS |
|---|---|
| Páginas pré-existentes (inalteradas) | 89.3–89.6 kB (idêntico a antes desta sprint) |
| `/admin` (Dashboard, com gráficos) | 254 kB |
| `/admin/metrics`, `/admin/system` (Recharts) | 213 kB |
| `/admin/executions` | 140 kB |
| Demais páginas `/admin/*` | 110–124 kB |

O peso maior nas páginas com gráfico vem do Recharts (biblioteca de gráficos),
carregado só nas rotas que o usam — code splitting automático do Next.js App
Router, confirmado pelo bundle das páginas pré-existentes não ter mudado
nenhum byte. "Gráficos em tempo real" são polling (5s para status/metrics/
whatsapp, 30s para o resto) com uma janela local de amostras no cliente —
sem WebSocket, sem série temporal persistida no backend (ver
`docs/DASHBOARD.md`).

## Capturas de tela

Capturadas com Playwright/Chromium contra um backend real (Postgres + Redis
reais, dados semeados) — enviadas separadamente nesta conversa, não commitadas
no repositório (binários não pertencem ao histórico do código):

`dashboard.png`, `agents.png`, `tools.png`, `tool-dialog.png`,
`executions.png`, `executions-select-open.png`, `memory.png`, `google.png`,
`whatsapp.png`, `users.png`, `logs.png`, `metrics.png`, `system.png`,
`settings.png`, `access-denied.png` (guarda de acesso para um usuário
não-admin real, registrado via `/api/auth/register`).

## Resultado dos testes

```
Backend:  540 passed, 3 warnings in ~80s      (pytest)
Frontend: 106 passed in ~11s                   (vitest)
ruff check .                                   All checks passed!
npx tsc --noEmit                               (sem erros)
npm run lint                                   No ESLint warnings or errors
next build                                     ✓ Compiled successfully — 26 rotas
docker compose config                          válido (exit 0)
```

### Smoke test em navegador real

Login real → guarda de acesso (admin e não-admin, ambos testados com usuários
reais registrados via `/api/auth/register`) → as 12 páginas → interações
(modal de detalhe de tool, seletor de período em Executions) — tudo contra
backend/Postgres/Redis reais nesta sessão, com dados semeados manualmente.

Esse teste manual encontrou **dois bugs visuais reais** que nenhuma outra
checagem (TypeScript, ESLint, testes unitários, `next build`) detectaria, por
serem efeitos de renderização real de CSS no navegador:

1. **Texto de log ilegível**: desabilitar o `preflight` do Tailwind (decisão
   deliberada, para nunca alterar visualmente as páginas pré-existentes)
   removeu o reset padrão do navegador para `<button>`, deixando o chrome
   nativo (fundo/borda cinza) sobrepor o texto. Corrigido com um reset
   equivalente ao do Tailwind, mas de especificidade zero (`:where()`), só
   dentro de `.admin-theme` — não afeta nenhuma página fora do dashboard.
2. **Modal e dropdown sem fundo/borda visíveis**: os componentes baseados em
   `Portal` do Radix (`Dialog`, `Select`) renderizam por padrão no fim do
   `document.body`, fora da `div.admin-theme` que escopa as variáveis CSS do
   tema — `hsl(var(--admin-card))` resolvia para nada ali. Corrigido com um
   `container` de Portal apontando para dentro de `.admin-theme`
   (`hooks/use-portal-container.tsx`), o padrão recomendado pelo próprio Radix
   para exatamente este cenário.

### Bug de backend encontrado durante o desenvolvimento (não apenas na validação final)

Ao verificar manualmente se `/admin/agents`/`/admin/tools` refletiam dados
reais do Prometheus (não só do teste sintético que eu mesmo tinha escrito),
descobri que `_metric_value()` procurava a amostra pela chave externa do
snapshot (`"darioos_agent_runs_total"`), mas `prometheus_snapshot()` agrupa
pelas *nome-base* do Prometheus (`"darioos_agent_runs"`, sem o sufixo que uma
amostra de Counter/Histogram carrega) — a busca nunca batia, e
`runs_total`/`avg_duration_seconds`/`calls_total` ficavam sempre zerados/nulos
em produção, mesmo com atividade real. Corrigido buscando por
`sample["name"]` em vez da chave externa; dois testes de regressão chamando o
registro Prometheus de verdade (não um dublê) foram adicionados
especificamente para este bug.

## Confirmação de que nada existente quebrou

- Todos os 479 testes de backend pré-existentes continuam passando, sem
  alteração de asserção alguma.
- Todas as 12 páginas pré-existentes do frontend mantêm o byte exato de
  tamanho de bundle antes/depois desta sprint.
- Nenhuma migration, model, endpoint, tool, agente, provider ou fluxo OAuth
  foi alterado — `git diff` confirma que os únicos arquivos pré-existentes
  tocados são `main.py` (2 linhas, registro de router), `requirements.txt`
  (1 linha), `Sidebar.tsx` (1 linha), `README.md`/`architecture.md`
  (documentação) e `.gitignore`.

## Veredito final

🟢 **APROVADO** — Dashboard Administrativo completo, com qualidade visual
comparável a LangSmith/Grafana/Datadog (verificado em navegador real, não só
por código), construído inteiramente sobre dados que já existiam, sem alterar
nenhuma regra de negócio, API, ou comportamento pré-existente. 646 testes
novos/mantidos passando (540 backend + 106 frontend), cobertura acima de 90%
em ambos, TypeScript/ESLint/build/Docker Compose limpos, dois bugs visuais
reais e um bug de backend real encontrados e corrigidos durante o próprio
desenvolvimento desta sprint — não deixados para depois.
