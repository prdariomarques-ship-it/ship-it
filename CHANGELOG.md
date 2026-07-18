# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

## [1.3.1] - 2026-07-18

Patch: resolve os dois achados Medium deixados em aberto por `RC1_AUDIT.md` — ambos explicitamente marcados como "precisam de decisão de produto, não fix mecânico". Sem funcionalidade nova, sem migração de banco, sem mudança de frontend. Análise completa: `RELEASE_READINESS.md`.

### Corrigido

- `agents/tools/domain.py::_add_store_customer` (tool de agente, alimentada por texto extraído do WhatsApp) gravava e-mail/telefone direto no banco sem validação nenhuma — plugado `validate_email`/`validate_phone_e164`, que existiam em `services/validation.py` mas não tinham nenhum chamador em lugar nenhum do backend.
- `validate_phone_e164` exigia `+` obrigatório (E.164 estrito), incompatível com a convenção real do produto — números vindos do WhatsApp chegam sem `+` (`normalize_phone()` remove), confirmado por um teste já existente (`test_contact_crud`, `"5511999999999"`). Corrigida para aceitar telefone com ou sem `+`, e agora também valida o campo `phone` em `ContactCreate/Update`, `ChurchMemberCreate/Update`, `StoreCustomerCreate/Update`.
- `POST /jobs/{id}/cancel` era uma duplicata inferior, sem chamador no frontend, de `POST /admin/jobs/{id}/cancel` (o que o dashboard de fato usa) — faltava lock de linha, log de auditoria e publicação de evento. Risco latente de corrida/lacuna de auditoria, não só código morto. Removido; `docs/api.md` atualizado.

### Removido

- `validate_url`/`validate_file_path` de `services/validation.py` — confirmado, por busca em todo o backend, que não existe nenhuma URL controlada por usuário buscada diretamente nem nenhum path vindo de request tocando o filesystem. Código morto desde sempre, não uma lacuna.

### Testes

864 testes de backend (-22 desde v1.3.0-rc1 — 21 pela remoção do código morto, líquido de pequenos ajustes nos testes de telefone), 100% passando, verificado com os caminhos reais do repositório. Frontend não tocado, 240 testes inalterados. Lint (`ruff`) limpo.

## [1.3.0] - 2026-07-18

GA da mesma leva de funcionalidades da `1.3.0-rc1` (ver abaixo). Inclui a correção do único achado Crítico da auditoria de release, que a RC ainda não tinha:

### Corrigido

- Sidebar do painel admin sem responsividade mobile (inutilizável em ~375px) — `AdminShell.tsx` ganhou um drawer com hambúrguer; layout desktop byte-a-byte inalterado. 9 testes novos. Prontidão de release: 82% (na RC) → 90% (após este fix). Ver `RC1_AUDIT.md`, `RC1_RELEASE_REPORT.md`.

### Testes

886 testes de backend (+3 desde a RC1, os novos testes de `GET /api/version`), 240 de frontend (+9, o drawer mobile), 100% passando.

## [1.3.0-rc1] - 2026-07-17

AI Operator Center, Memory & Timeline, Daily Briefing, Action Center — o dashboard deixa de ser um painel de leitura e passa a responder "o que eu devo fazer agora?" e a executar a resposta. Sem alteração de arquitetura backend além do estritamente necessário para cada funcionalidade (ver justificativa de cada endpoint novo abaixo). Auditoria de release: `RC1_AUDIT.md`.

### Adicionado

- **AI Operator Center** (`/admin`, seção topo): sintetiza metas, tarefas, agenda, jobs e o Contexto Atual em recomendações agrupadas por urgência (🔥 urgente / ⚠️ hoje / 💡 oportunidade / 🤖 automação), cada uma com motivo, confiança (tiers fixos 95/65/35, nunca uma probabilidade inventada), impacto esperado e tempo estimado. Zero chamada a LLM no caminho crítico — cada insight é uma regra determinística sobre dados reais. Detalhes: `AI_OPERATOR.md`.
- **Memory & Timeline** (`/admin/timeline`): transforma o log de auditoria bruto em memória operacional — oito seções por assunto (conversas, metas, tarefas, agenda, WhatsApp, decisões da IA, eventos do sistema, Observation Engine), cada evento com por-quê, consequência e entidades relacionadas. Filtros por dia-calendário real (Hoje/Ontem/7 dias/30 dias/Tudo — não uma janela de 48h fixa) e "o que mudou desde ontem/desde meu último login". Corrige um bug real de produção: `job:observation.tick` (2 linhas a cada poucos minutos) podia expulsar eventos raros de uma página de 1000 linhas antes mesmo de chegar ao frontend — `exclude_source` em `/admin/logs` agora filtra na query, não depois do `limit`. Detalhes: `MEMORY_TIMELINE.md`.
- **Daily Briefing** (`/admin/briefing`): briefing executivo narrativo — parágrafo de abertura, resumo executivo, prioridades/riscos/oportunidades com "por que agora"/"consequência se ignorado", plano de execução Manhã/Tarde/Noite (sugestão por urgência, nunca uma agenda imposta), saúde do dia (0-100, fórmula de 6 fatores totalmente auditável na própria UI). Detalhes: `DAILY_BRIEFING.md`.
- **Action Center** (`/admin/action-center`): toda recomendação agora expõe um workflow executável de verdade — concluir/adiar tarefa, aprovar meta, reenviar job falhado, criar tarefa de acompanhamento, agendar tempo na agenda — cada um classificado `SAFE_AUTOMATIC` (um clique), `REQUIRES_CONFIRMATION` (dois cliques, com **Action Preview**: o que vai acontecer, o que é afetado, se pode ser desfeito, tempo estimado, efeitos colaterais, confiança de execução) ou `MANUAL_ONLY` (link + explicação de por que o sistema não decide sozinho). Automation Score (ações concluídas hoje, minutos economizados, confirmações pendentes) derivado só de execuções reais registradas, nunca de estimativa sem evidência. Histórico de execução exposto na Timeline já existente, sem subsistema novo. Detalhes: `ACTION_CENTER.md`.
- `POST /admin/actions/log`: registra a execução de uma ação do Action Center no mesmo `logs`/Event Bus já usado por `admin_cancel_job`/`admin_retry_job` — nenhuma tabela nova.
- `source_prefix` em `GET /admin/logs`: necessário porque cada tipo de ação grava sob sua própria fonte exata (`admin:action.complete_task`, `admin:action.retry_job`, ...) — não existe um único `source` que signifique "todo log de ação".
- `since`/`until`/`exclude_source` em `GET /admin/logs` (Memory & Timeline).

### Corrigido

- `_TaskRepo` duplicado byte-a-byte de `repositories/task.py::TaskRepository` em `agents/tools/productivity.py` — mesma classe de duplicação já corrigida uma vez para outros dois arquivos, esta terceira ocorrência havia passado despercebida.
- Quatro pontos reimplementando `new Date(iso).toLocaleString("pt-BR")` em vez do já existente `lib/format.ts::formatDateTime` (que também adiciona proteção contra null) — consolidados.
- Race condition no Action Center: o Automation Score e a lista "Concluídas" podiam mostrar dado desatualizado logo após uma ação bem-sucedida, porque a invalidação de `admin.logs` disparava antes do registro de auditoria (deliberadamente fire-and-forget) realmente ter sido gravado. Corrigido encadeando a invalidação na promise da própria escrita.
- Bug de fuso horário no plano de execução do Daily Briefing: `periodForHour` usava `.getHours()` (hora local) em vez de `.getUTCHours()`, inconsistente com todo o resto do código (`lib/timeline.ts`).
- `buildCalendarEvents` do Timeline sempre tratava `since === undefined` como "sempre criado, nunca atualizado" — a visão "Tudo" nunca conseguia mostrar um evento atualizado, não importa o quão óbvio fosse.

### Testes

883 testes de backend (+6 desde v1.2.0), 231 testes de frontend (+123 desde v1.2.0). `tsc --noEmit`, `next lint` e `next build` limpos. Validado em navegador contra ambiente demo isolado (banco SQLite seedado com dados realistas), zero erros de console na passagem final.

### Observações

Ver `RC1_AUDIT.md` para a auditoria completa de release: 1 achado crítico (sidebar do painel admin sem responsividade mobile — não corrigido nesta versão, ver o próprio documento para o porquê), achados médios e menores, medições de performance (tempo de start do backend, latência de API, tamanho de bundle) e prontidão de release estimada em 82%.

## [1.2.0] - 2026-07-11

Dashboard Administrativo e Production Hardening — sem novas funcionalidades
de usuário, sem alteração de regras de negócio.

### Adicionado

- **Dashboard Administrativo** (`/admin`, exclusivo `role=admin`): status dos
  sistemas, agentes e tools registrados, timeline de execuções, memória
  (Qdrant/embeddings), Google Workspace, WhatsApp, usuários, logs, métricas e
  informações de sistema. Construído inteiramente sobre dados que já
  existiam (Agent/Tool Registry, métricas Prometheus). 12 rotas somente
  leitura em `/api/admin/*`. Detalhes: `docs/DASHBOARD.md`.
- **Correlation/Request ID**: `X-Request-ID` gerado ou ecoado em toda
  requisição/resposta, propagado a todo log emitido durante ela.
- **Tracing distribuído (OpenTelemetry)**: opcional, desligado por padrão
  (zero overhead); auto-instrumenta FastAPI, SQLAlchemy e httpx quando
  ligado.
- **Suíte E2E (Playwright)**: 23 testes cobrindo login, responsividade,
  acessibilidade (`@axe-core/playwright`), navegação por teclado,
  loading/error states e performance.
- Bundle analyzer do frontend sob demanda (`ANALYZE=true npm run build`).

### Corrigido

- `MemoryService.search()` chamava um método (`AsyncQdrantClient.search()`)
  removido do `qdrant-client` a partir da 1.18 — toda busca semântica de
  memória quebrava com `AttributeError` em produção. Substituído por
  `query_points()`.
- Login com credenciais erradas não mostrava o erro inline: `apiFetch`
  tratava qualquer 401 (inclusive o de uma tentativa de login sem token)
  como sessão expirada e redirecionava para `/login` antes do erro
  renderizar.
- `favicon.ico` ausente (404 em toda carga de página).
- 3 violações WCAG 2 AA de contraste de cor e 1 região rolável sem foco por
  teclado no Dashboard Administrativo.
- Overflow horizontal em telas mobile (sidebar principal sem media query).

### Testes

555 testes de backend (94% de cobertura), 108 testes de frontend, 23
testes E2E (Playwright).

### Observações

Ver `SPRINT5_REPORT.md` (Production Hardening) e `DASHBOARD_REPORT.md`
(Dashboard Administrativo) para os relatórios completos.

## [1.1.2] - 2026-07-10

### Corrigido

- Migrations do Alembic dependiam do `CREATE TYPE` implícito do
  SQLAlchemy/asyncpg para os `ENUM` do Postgres, que só é emitido pela
  *primeira* migration que referencia cada tipo — uma migration posterior
  que reutilizasse o mesmo `ENUM` (ex.: `messagedeliverystatus`) falhava
  com `UndefinedObjectError` em qualquer banco que ainda não tivesse
  aplicado a revisão original. Migrations passaram a criar os tipos `ENUM`
  do Postgres explicitamente. Ver `MIGRATION_FIX_REPORT.md`.

## [1.1.1] - 2026-07-10

Google Workspace: Gmail, Google Calendar, Google Contacts e Google Drive
como base de conhecimento — quatro domínios novos e isolados, cada um
com seu próprio fluxo OAuth, acessíveis apenas pelo agente `assistant`
(gateway único).

### Adicionado

- **E-mail (Gmail)** — Sprint 1: leitura, busca, resumo e detecção de
  pendências em e-mails; somente leitura (enviar/responder/mover/excluir
  fora do escopo).
- **Google Calendar** e **Google Contacts** — Sprint 2: leitura e escrita
  (listar, buscar, criar, editar, excluir, verificar disponibilidade);
  domínios completamente separados da agenda/contatos internos do Dario OS.
- **Google Drive** — Sprint 3: base de conhecimento — lista, busca, lê
  (PDF, DOCX, TXT, Markdown, CSV) e indexa arquivos na mesma coleção Qdrant
  já existente (`source="knowledge"`); `MemoryManager.forget` novo,
  genérico, usado pela reindexação para substituir pedaços obsoletos.
- Reaproveitamento do mesmo app OAuth do Google Cloud entre os quatro
  domínios (só muda a URI de redirecionamento e o escopo por domínio).

### Corrigido

- XSS refletido e corrida de conexão na integração Gmail (auditoria
  Sprint 1.1).
- Vetores órfãos no Qdrant e uma vulnerabilidade de path traversal na
  plataforma Google, encontrados na auditoria final antes do code freeze.

### Observações

Aprovado para produção (code freeze v1.1.1). Ver `GOOGLE_PLATFORM_AUDIT.md`
e `SPRINT_1_1_VALIDATION.md`.

## [1.0.0] - 2026-07-10

Primeira versão do Dario OS — sistema operacional pessoal baseado em IA (WhatsApp, agenda, tarefas, loja, igreja e memória permanente).

### Adicionado

- Plataforma base: backend FastAPI (Python 3.12, SQLAlchemy 2 async, Alembic), dashboard Next.js 14, Docker Compose completo (Postgres, Redis, Qdrant, n8n, Caddy com HTTPS automático).
- 5 agentes de IA com function calling: `personal`, `church`, `store`, `content`, `assistant`.
- Memória permanente: Qdrant (busca semântica) + Postgres (histórico estruturado), com resumo automático de contato e preferências estruturadas.
- 4 Providers de WhatsApp plugáveis (Strategy + Factory): OpenWA, Baileys, Evolution API, WhatsApp Cloud API oficial — troca por configuração, sem mudar código.
- 5 Providers de LLM plugáveis: OpenAI, Anthropic, GLM, Gemini, Ollama.
- Autenticação JWT + refresh token rotativo + RBAC (admin/user).
- Fila de jobs durável (Postgres), com retry exponencial e claim atômico entre múltiplos workers.
- **Agent Registry** e **Tool Registry** com auto-descoberta por convenção de pasta — instalar um agente ou ferramenta nova nunca exige editar um arquivo central.
- **Event Bus** (pub/sub interno + fan-out best-effort via Redis).
- **AI Orchestrator**: ponto único de seleção de agente, execução, timeout e métricas.
- **Memory Manager**: fachada única sobre memória de curto prazo, longo prazo, conhecimento, preferências e resumo.
- **Fluxo WhatsApp ponta a ponta**: mensagem recebida → job → pipeline → agente → resposta → envio, sem depender de automação externa (n8n continua disponível em paralelo).
- **Cognitive Pipeline**: Intent Engine e Priority Engine (classificação por function calling, com degradação heurística honesta), Cognitive Planner (decompõe um pedido em até 5 etapas, escolhe o agente de cada uma, decide quando pedir confirmação), Response Validator (com retry bounded) e Learning Engine (tagueia domínios recorrentes do contato).
- Troca automática de provider de LLM em caso de falha (`LLM_FALLBACK_PROVIDER`).
- Prioridade de execução real: mensagens urgentes furam a fila de jobs.
- Observabilidade: logs estruturados em JSON, 16 métricas Prometheus, health/readiness com degradação graciosa por dependência.
- Documentação completa: `README.md`, `docs/architecture.md`, `docs/AGENTS.md`, `docs/TOOLS.md`, `docs/MEMORY.md`, `docs/WORKFLOWS.md`, `docs/api.md`, relatórios técnicos por fase.

### Corrigido

- `MissingGreenlet` no worker de jobs quando um lote continha múltiplos jobs e um deles falhava antes de outro.
- `AttributeError` em três Providers de WhatsApp (OpenWA, Baileys, Evolution) ao receber um payload malformado com `"data": null`.
- Falha de memória semântica (Qdrant indisponível) não protegida no carregamento de contexto do Cognitive Pipeline — derrubava o pipeline inteiro.
- Exceção levantada por um provider de LLM não disparava a degradação heurística de intenção/prioridade/planejamento.
- Job de envio de WhatsApp (`whatsapp.send_text`) pulava persistência e memória quando disparado pela fila (só o caminho via API fazia isso corretamente).

### Segurança

- **PROD-004**: `WEBHOOK_SECRET` passou a ser obrigatório em produção — o backend recusa o boot sem um valor forte (≥ 32 caracteres), mesmo padrão já aplicado a `JWT_SECRET`. `docker-compose.yml` exige a variável; `scripts/setup.sh` gera ambas automaticamente na primeira instalação.
- **PROD-005**: isolamento técnico de contato nas ferramentas `send_whatsapp_message` e `find_contact` — uma conversa só pode agir sobre o seu próprio contato, decidido em código (`ToolContext.contact_id`, nunca escolhido pelo LLM), não por instrução de prompt.
- Assinatura HMAC-SHA256 real para o provider oficial de WhatsApp (Meta, `X-Hub-Signature-256`).
- Hashing de senha PBKDF2-HMAC-SHA256 (390k iterações) com salt aleatório e comparação em tempo constante; timing equalizado para e-mail inexistente no login.
- Refresh tokens armazenados como hash SHA-256, rotativos, com rejeição de reuso.
- RBAC aplicado nas rotas administrativas (`/api/jobs`, `/api/logs`); CORS com allow-list explícita.
- Rate limiting por IP, reaproveitado como freio de loop/flood no auto-reply do WhatsApp.
- Deduplicação de mensagens de WhatsApp (idempotência por `external_id` + constraint única no banco).

### Testes

246 testes passando
92% de cobertura de linha

### Observações

Primeira versão aprovada para produção. Ver `PRODUCTION_APPROVAL.md` (auditoria final, 12 seções) e `PRODUCTION_BLOCKERS_RESOLVED.md` (correção dos dois bloqueadores encontrados) para o relatório completo. Notas de release detalhadas: `RELEASE_NOTES_v1.0.md`.
