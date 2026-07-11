# ⚠️ DEPRECATED: Use ARCHITECTURE_FINAL.md instead

**This document is superseded and no longer the authoritative source.**

Refer to the following documents instead:
- **Primary**: See `ARCHITECTURE_FINAL.md` (root) — consolidated authoritative architecture
- **For module details**: See `MODULE_CATALOG.md` (root)
- **For architectural decisions**: See `ARCHITECTURE_DECISIONS.md` (root)
- **For AI roles and governance**: See `AI_GOVERNANCE.md` (root)
- **For migration phases**: See `ARCHITECTURE_MIGRATION_PLAN.md` (root)

---

# Dario Platform — Arquitetura

Documento de especificação arquitetural. Registra a visão de longo prazo
da Dario Platform e como ela se relaciona com o Dario OS existente
(Core). **Este documento é planejamento — nenhum módulo aqui descrito
foi implementado.** Para o que já existe e está em produção, ver
`docs/architecture.md` (arquitetura do Core, inalterada por este
documento) e `PROJECT_STATUS.md`.

Duas decisões seguem em aberto e não estão resolvidas por este
documento — ver "Decisões pendentes" no final.

## Visão

Centralizar toda a operação profissional de Dario Marques Neto em um
único ecossistema: trabalho, clientes, investimentos, inteligência
artificial, conteúdo, pesquisa, automações, documentos, conhecimento,
negócios e produtividade.

O Dario OS — tudo que existe hoje (Orchestrator, Agents, Memory, Event
Bus, Dashboard, Tool Registry, Providers) — deixa de ser o produto e
passa a ser o **Core** da Dario Platform: a infraestrutura compartilhada
sobre a qual todo módulo novo é construído.

## Princípio arquitetural central

**A plataforma não precisa de uma arquitetura nova — precisa continuar
aplicando a que já existe, em mais domínios.** O padrão de plugin já foi
provado 4 vezes no Core (WhatsApp Providers, LLM Providers, Google
Workspace, Admin Dashboard): um domínio novo se instala por convenção de
pasta, sem editar nenhum arquivo central. Cada módulo novo da plataforma
segue exatamente essa disciplina.

## Decisão de topologia: monolito modular

Um backend deployável, um frontend deployável. Fronteiras impostas por
código e contrato, não por rede — não microsserviços.

**Justificativa** (aplicando o teste "esta alteração aproxima ou afasta a
visão de longo prazo"): dividir em microsserviços agora **afastaria** —
multiplica containers, modos de falha de rede e coordenação de deploy
sem nenhum ganho real (não há time crescendo, não há necessidade de
escalar um módulo independente do outro, o operador é único). Um
monolito modular bem desenhado **aproxima** — cada módulo sai mais
rápido e mais barato, e a opção de extrair um módulo para serviço próprio
no futuro continua aberta, desde que a disciplina de fronteira abaixo
seja seguida desde o primeiro módulo.

## Regra de dependência

**Core nunca importa de módulo. Módulo sempre pode importar de Core.
Nunca o contrário.** `orchestrator/`, `agents/`, `events/`, `memory/`,
`providers/` — nenhum desses pacotes referencia `business/`,
`investments/`, ou qualquer outro módulo, em nenhuma linha. O Core
continua testável e deployável isoladamente para sempre, não importa
quantos módulos existam por cima.

## Como módulos se comunicam

Nunca lendo a tabela de outro módulo diretamente. Três canais, nesta
ordem de preferência:

1. **Event Bus** (já existe) — canal default para qualquer coisa
   assíncrona ou desacoplada.
2. **Orchestrator/Agent** — quando a ação cruzada precisa ser síncrona
   dentro de um fluxo conversacional.
3. **Serviço público versionado do módulo** — quando um módulo precisa de
   um dado síncrono de outro, chamando a função pública do serviço, nunca
   o repositório/modelo ORM do outro módulo diretamente.

## Módulos da plataforma

| Módulo | Escopo | Risco de construir | Seed existente no Core |
|---|---|---|---|
| **Core** (Dario OS) | Orchestrator, Agents, Memory, Event Bus, Dashboard, Tool Registry, AI Engine | — | É o próprio Core |
| **Business** | CRM, Pipeline, Agenda, Clientes, Follow-up, Projetos, KPIs | Médio | `store_agent`/`store_customers` |
| **Investments** | Carteiras, Fundos, ETFs, Crédito Privado, Cenário Macro, Relatórios, Inside Diário | Alto (dado sensível, possível peso regulatório) | Nenhum |
| **Content Studio** | Instagram, LinkedIn, YouTube, Newsletter, Blog, Reels, Carrosséis, Stories, Copywriting | Médio-alto | Nenhum |
| **Research Lab** | RFC, ADR, Benchmarks, Roadmaps, Estudos, Experimentação | Médio (processo, não código pesado) | Os próprios relatórios de sprint já produzidos |
| **Automation** | Workflows, Scheduler, Jobs, Integrações | Baixo | Fila de jobs + n8n já existentes |
| **Knowledge** | Biblioteca, PDFs, Documentos, Prompt Library, Pesquisas | Baixo | Google Drive + tag `knowledge` da memória |
| **Admin** | Observabilidade, Logs, Configurações, Usuários, Releases, Monitoramento | — | Já existe (Sprint 4) — cresce de escopo, não é módulo novo |

## Árvore completa — backend

```
backend/
  # ===== CORE (Dario OS) — inalterado, zero import de módulo =====
  api/  auth/  orchestrator/  agents/  events/  chat/  memory/  jobs/
  mail/  gcalendar/  gcontacts/  gdrive/
  providers/{llm,whatsapp,mail,calendar,contacts,drive}/
  repositories/  observability/  services/  webhooks/  workflows/
  database/  models/  utils/  alembic/  tests/
  admin/                          # já existe — cresce de escopo

  # ===== MÓDULOS DA PLATAFORMA (especificação) =====
  business/
    models.py                     # Client, Deal, FollowUp, Project, KPI
    repositories.py  service.py  router.py     # /api/business/*
    agents/crm_agent.py           # @register_agent, mesma convenção do Core
    tools/crm_tools.py            # find_client, create_deal, schedule_followup
    providers/hubspot/provider.py # implementa CRMProvider
    providers/factory.py
    tests/

  investments/
    models.py                     # Portfolio, Holding, Fund, ETF, MacroScenario, Report
    repositories.py  service.py  router.py     # /api/investments/*
    agents/portfolio_agent.py
    tools/investment_tools.py
    providers/b3_data/provider.py     # implementa MarketDataProvider
    providers/bcb_macro/provider.py   # implementa MacroDataProvider
    providers/factory.py
    tests/

  content_studio/
    models.py                     # ContentPiece, Channel, EditorialCalendar, Draft
    repositories.py  service.py  router.py     # /api/content-studio/*
    agents/{copywriter_agent.py, designer_agent.py}
    tools/content_tools.py        # draft_post, generate_carousel, schedule_post
    providers/{canva,instagram,linkedin}/provider.py
    providers/factory.py
    tests/

  research_lab/
    models.py                     # RFC, ADR, Benchmark, Experiment
    repositories.py  service.py  router.py     # /api/research-lab/*
    tests/                        # sem agents/tools — é processo, não automação

  automation/
    scheduler.py                  # cron-like; publica na fila de jobs já existente
    router.py                     # /api/automation/* — visibilidade + CRUD de agendamentos
    tests/                        # evolução de jobs/+workflows/, não pacote paralelo

  knowledge/
    models.py                     # KnowledgeSource, PromptTemplate — não duplica Embedding
    repositories.py  service.py  router.py     # /api/knowledge/*
    tools/knowledge_tools.py      # save_prompt, list_sources
    tests/
```

## Árvore completa — frontend

```
frontend/app/
  (dashboard)/          # Core — inalterado
  admin/                # Core — cresce de escopo
  login/
  (business)/{clientes, pipeline, follow-up, projetos}/
  (investments)/{carteiras, cenario-macro, relatorios}/
  (content-studio)/{calendario, canais, copywriting}/
  (research-lab)/{rfcs, adrs, benchmarks}/
  (automation)/{agendamentos, workflows}/
  (knowledge)/{biblioteca, prompts}/

frontend/components/{business,investments,content-studio,research-lab,automation,knowledge}/
  # mesmo padrão de components/admin/ hoje
```

## Contrato formal de módulo

Todo módulo novo, sem exceção, cumpre isto:

| Obrigação | Mecanismo já existente que se reaplica |
|---|---|
| Expor rotas com prefixo próprio | `app.include_router(x_router, prefix="/api/business")`, igual a todo router hoje |
| Dono exclusivo dos seus modelos | `business/models.py`, sem FK direta para tabela de outro módulo |
| Capacidade conversacional (se houver) | `agents/` + `tools/` no padrão `@register_agent`/`Tool(...)` — auto-descoberta sem editar registry central |
| Integração externa | `providers/<nome>/provider.py` implementando um `Protocol` documentado, resolvido por `factory.py` — nunca SDK de terceiro importado fora do provider |
| Comunicação com outro módulo | Event Bus (`<módulo>.<evento>`) por padrão; Orchestrator quando síncrono dentro de um plano de agente; serviço público versionado como último recurso |
| Visibilidade no Admin | Um `manifest.py` mínimo (nome, versão, status) — extensão do mesmo princípio de auto-descoberta do Agent/Tool Registry, um nível acima, no módulo inteiro |

## Catálogo de eventos — fluxos de exemplo da visão

**Fluxo 1** (cliente → proposta → apresentação → follow-up → WhatsApp → relatório):
```
business.client_profile_analyzed
business.proposal_requested
content_studio.presentation_generated
business.followup_scheduled
whatsapp.send_text            # job já existente, reaproveitado sem mudança
business.report_generated
```

**Fluxo 2** (notícia macro → Inside Diário → PDF → carrossel → vídeo → post → métricas):
```
knowledge.news_ingested
investments.macro_scenario_updated
investments.daily_report_generated
content_studio.pdf_generated
content_studio.carousel_generated
content_studio.video_generated
content_studio.post_scheduled
content_studio.metrics_tracked
```

**Fluxo 3** (research → RFC → arquitetura → implementação → testes → release):
```
research_lab.experiment_completed
research_lab.rfc_drafted
research_lab.rfc_approved        # gate humano obrigatório, nunca automático
release.shipped                  # Admin já tem noção de release (git describe) — estende
```

Nenhum evento aqui exige infraestrutura nova — é nomenclatura sobre o
Event Bus que já existe.

## Mapa de posse de dados

| Módulo | Tabelas próprias | Nunca toca |
|---|---|---|
| Business | `clients`, `deals`, `followups`, `projects`, `kpis` | `store_customers`/`church_members` (decisão pendente) |
| Investments | `portfolios`, `holdings`, `funds`, `macro_scenarios`, `reports` | Nenhuma tabela de Core |
| Content Studio | `content_pieces`, `channels`, `editorial_calendar`, `drafts` | `embeddings` (Memory Manager escreve lá, não Content Studio direto) |
| Research Lab | `rfcs`, `adrs`, `benchmarks`, `experiments` | Nenhuma |
| Automation | Nenhuma tabela nova — usa `jobs` já existente | — |
| Knowledge | `knowledge_sources`, `prompt_templates` | `embeddings`, `google_drive_indexed_files` (lê via Memory Manager, não duplica) |

## Providers — governança

Toda integração externa nova (HubSpot, Canva, dados de mercado, APIs de
publicação) é obrigatoriamente Strategy+Factory, exatamente como LLM e
WhatsApp hoje. Nenhum router ou service importa um SDK de terceiro
diretamente — só a implementação do Provider correspondente pode.

Integrações já disponíveis no ambiente de desenvolvimento atual e que
mapeiam diretamente para módulos (aceleram a estimativa de esforço real):

| Módulo | Integração já conectada |
|---|---|
| Business | HubSpot |
| Content Studio | Adobe for Creativity, Canva, Figma, Gamma |
| Research Lab | Busca/leitura web |

Investments não tem nenhuma integração de dados de mercado conectada
ainda — maior lacuna a resolver antes desse módulo começar.

## Migrações

Uma única história do Alembic (menor custo operacional que múltiplas),
mas toda revisão de módulo novo nasce com o nome prefixado por módulo
(`business: adiciona tabela clients`). Disciplina **expand-contract**
obrigatória desde a primeira migração de cada módulo: adicionar coluna
nullable → backfill → tornar obrigatória numa release seguinte. Garante
que uma migração de módulo nunca impede um rollback de emergência do
Core.

## Observabilidade — convenção estendida

Mesmo prefixo `darioos_`, mesmo estilo de label já usado hoje:

```
darioos_business_deals_total{stage,status}
darioos_business_followups_total{status}
darioos_investments_portfolio_value_brl{portfolio}
darioos_investments_report_generation_seconds
darioos_content_studio_posts_published_total{channel,status}
darioos_content_studio_generation_duration_seconds{asset_type}
darioos_automation_scheduled_jobs_total{status}
darioos_knowledge_sources_indexed_total
```

**Gap real identificado, ainda sem solução**: o Correlation/Request ID
de hoje vive por requisição HTTP. Fluxos multi-etapa que atravessam
Event Bus e fila de jobs (Fluxos 1 e 2 acima) precisam de um **Flow ID**
que persiste através de várias mensagens de evento e execuções de job —
não é uma extensão trivial do Request ID atual. Provavelmente resolvido
junto do módulo Automation, quando o Scheduler entrar.

## Engenharia de produção

- **CI**: continua um pipeline único enquanto couber no tempo de
  execução aceitável. Quando justificar, CI por caminho de arquivo
  alterado para a suíte do módulo específico — mas a suíte completa do
  Core roda sempre, em todo PR, porque é a dependência compartilhada de
  tudo.
- **Testes**: mesma disciplina de `CONTRIBUTING.md` por módulo — mockar a
  borda externa (Provider), nunca a própria lógica. Adicionar testes de
  contrato entre Core e módulo (payload de evento não muda de formato
  silenciosamente).
- **E2E**: suíte Playwright roda contra build de produção
  (`npm run build && npm start`), nunca contra `next dev` — elimina a
  classe de flake de cold-start já observada nas sprints anteriores.
- **Feature flags**: todo módulo novo nasce atrás de uma flag (padrão
  env-var, mesmo estilo de `OTEL_ENABLED`) — habilitável/desabilitável
  sem novo deploy. Especialmente importante para Investments (maior
  risco).
- **Rollback**: mudança de módulo = reverter código + redeploy do
  container, contanto que as migrações do módulo sigam expand-contract.
  Nenhuma extração para serviço próprio deveria ser necessária para
  reverter um módulo problemático.

## Governança técnica

Todo RFC em `research_lab/` que toque fronteira entre Core e módulo,
contrato de Event Bus, ou modelo de dado compartilhado, responde
explicitamente, como seção obrigatória do próprio documento: **"esta
alteração aproxima ou afasta a Dario Platform da visão de longo
prazo?"** — critério de aceite do RFC, não reflexão informal.

## Roadmap — 24 meses

| Trimestre | Foco | Depende de |
|---|---|---|
| T1 (0–3m) | Fechar v1.2.1 (CSP/HSTS) e v1.3.0 (retry/circuit breaker Google). Formalizar processo de RFC/ADR (Research Lab v0, só processo). | Nada — já planejado |
| T2 (3–6m) | **Knowledge v1** — expandir base além do Drive, Prompt Library. | Core estável |
| T3 (6–9m) | **Automation v1** — Scheduler (já no roadmap v1.4.0), visibilidade de fila no Admin. | Core estável |
| T4 (9–12m) | **Business v1** — decisão sobre `store_agent` primeiro; CRM sobre Event Bus/Memory existentes. | Decisão church/store; Knowledge para RAG de cliente |
| T5 (12–15m) | **Content Studio v1** — copywriting + 1–2 canais, usando Canva/Adobe já disponíveis. | Business (perfil de cliente alimenta conteúdo) |
| T6 (15–18m) | **Investments v1, escopo pessoal apenas** — adia questão regulatória. | Provedor de dados de mercado ainda a escolher |
| T7 (18–21m) | **Multi-Agent** (v2.0.0 do roadmap do Core) — colaboração entre agentes de módulos diferentes. | Business + Content Studio maduros |
| T8 (21–24m) | Admin de plataforma completo — KPIs cruzados, Self Healing/Memory Evolution aplicados com dado real de uso multi-módulo. | Todos os módulos acima em uso real |

## Maiores riscos técnicos

1. Explosão de escopo — mitigado por um módulo por vez, nunca em paralelo.
2. Investments carrega peso regulatório potencial se algum dia servir terceiros — T6 adia isso escopando para uso pessoal.
3. Ambiguidade dono-único vs. multi-cliente — RBAC atual não modela "cliente" como sujeito de dado.
4. Colisão de modelo de dados com `store_customers`/`church_members`.
5. Sprawl de Providers sem disciplina Strategy+Factory.
6. Dívida de teste escalando — 7 módulos no mesmo rigor de hoje é investimento contínuo, não tarefa única.
7. Complexidade do Orchestrator/Planner com 15–20 agentes possíveis.
8. Superfície de segurança maior (dado de cliente, dado financeiro) exige o mesmo padrão de isolamento técnico do PROD-005, estendido.

## Maiores oportunidades estratégicas

1. Padrão de plugin já provado 4 vezes — adicionar módulo é arquiteturalmente barato.
2. Integrações já conectadas no ambiente (HubSpot, Canva, Adobe, Figma, Gamma) aceleram Business e Content Studio de forma concreta.
3. Memory Manager + Event Bus já entregam a experiência cross-domain que os Fluxos 1 e 2 pedem — é reaproveitamento, não construção nova.
4. Cultura de observabilidade desde o dia um evita o retrabalho típico do segundo ano de uma plataforma em crescimento.
5. Disciplina de mudança mínima e documentação permanente já é hábito — Research Lab formaliza o que já se pratica.
6. Ser dono único da operação hoje permite adiar complexidade multi-tenant sem perder velocidade de entrega de valor.

## Decisões pendentes

1. **`church_agent`/`store_agent`** — evoluem para dentro de `business/` (aproveitando `store_customers` como seed) ou ficam como estão, fora da nova taxonomia?
2. **VULN-1/BUG-1** (Sprint v1.2.1, já aprovada) — quando retomar a implementação, em relação ao fechamento desta visão de plataforma?

## Referências

- `docs/architecture.md` — arquitetura do Core (Dario OS), inalterada
- `ROADMAP_v2.md` — roadmap do Core (v1.2.1 → v2.0.0), referenciado pelo roadmap de plataforma acima
- `CONTRIBUTING.md` — convenções de Agent/Tool/Provider que todo módulo reaplica
- `TECHNICAL_DEBT.md` / `KNOWN_LIMITATIONS.md` — dívida e limitações do Core
