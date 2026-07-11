# ⚠️ DEPRECATED: Use MODULE_CATALOG.md (root) instead

**This document is superseded and no longer the authoritative source.**

Refer to `MODULE_CATALOG.md` in the repository root instead. It contains:
- Updated module definitions (4 modules, not 7)
- Current responsibility boundaries
- Data ownership mappings
- Event catalogs
- Integration documentation

For architectural context and decisions, see:
- `ARCHITECTURE_FINAL.md` (root) — consolidated architecture
- `ARCHITECTURE_DECISIONS.md` (root) — architectural decisions
- `AI_GOVERNANCE.md` (root) — roles and approval processes

---

# Dario Platform — Module Catalog

Catálogo técnico dos módulos da Dario Platform: árvore de diretórios,
contrato formal, mapa de posse de dados, catálogo de eventos e
integrações já disponíveis. Para o contexto/visão, ver
`docs/architecture/MASTER_CONTEXT.md`. Para decisões e justificativas,
ver `docs/architecture/ARCHITECT_DECISIONS.md`.

**Planejamento — nenhum módulo aqui descrito foi implementado.**

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
| Integração externa | `providers/<nome>/provider.py` implementando um `Protocol` documentado, resolvido por `factory.py` (ver AD-004) |
| Comunicação com outro módulo | Event Bus (`<módulo>.<evento>`) por padrão; Orchestrator quando síncrono; serviço público versionado como último recurso (ver AD-003) |
| Visibilidade no Admin | Um `manifest.py` mínimo (nome, versão, status) — extensão do princípio de auto-descoberta do Agent/Tool Registry, um nível acima |

## Mapa de posse de dados

| Módulo | Tabelas próprias | Nunca toca |
|---|---|---|
| Business | `clients`, `deals`, `followups`, `projects`, `kpis` | `store_customers`/`church_members` (decisão pendente — ver `ARCHITECT_DECISIONS.md`) |
| Investments | `portfolios`, `holdings`, `funds`, `macro_scenarios`, `reports` | Nenhuma tabela de Core |
| Content Studio | `content_pieces`, `channels`, `editorial_calendar`, `drafts` | `embeddings` (Memory Manager escreve lá, não Content Studio direto) |
| Research Lab | `rfcs`, `adrs`, `benchmarks`, `experiments` | Nenhuma |
| Automation | Nenhuma tabela nova — usa `jobs` já existente | — |
| Knowledge | `knowledge_sources`, `prompt_templates` | `embeddings`, `google_drive_indexed_files` (lê via Memory Manager, não duplica) |

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

## Métricas — convenção estendida

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

Ver AD-006 em `docs/architecture/ARCHITECT_DECISIONS.md` para o gap de
Flow ID ainda não resolvido.

## Integrações já disponíveis no ambiente de desenvolvimento

Mapeiam diretamente para módulos e aceleram a estimativa de esforço real
(não hipotética):

| Módulo | Integração já conectada |
|---|---|
| Business | HubSpot |
| Content Studio | Adobe for Creativity, Canva, Figma, Gamma |
| Research Lab | Busca/leitura web |

Investments não tem nenhuma integração de dados de mercado conectada
ainda — maior lacuna a resolver antes desse módulo começar (ver
`docs/roadmap/ROADMAP_24_MONTHS.md`, T6).
