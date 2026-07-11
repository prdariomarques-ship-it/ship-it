# Dario Platform — Module Catalog

Catálogo definitivo dos módulos da Dario Platform, consolidado a partir
de `ARCHITECTURE_FINAL.md`. Substitui, como referência corrente,
`docs/modulos/MODULE_CATALOG.md` — que permanece no repositório (não foi
movido nem apagado nesta etapa) mas contém a versão anterior à
consolidação, com 7 módulos em vez de 4. Ver "Riscos remanescentes" no
relatório desta etapa para essa duplicação ainda não resolvida
fisicamente.

**Planejamento — nenhum módulo aqui descrito foi implementado.**

---

## Core (Dario OS)

**Objetivo**: infraestrutura compartilhada sobre a qual todo módulo de
plataforma é construído.

**Responsabilidades**: Orchestrator, Cognitive Pipeline, Agent Registry,
Tool Registry, Event Bus, Memory Manager, Providers (LLM, WhatsApp,
Mail, Calendar, Contacts, Drive), fila de jobs durável, autenticação/
RBAC, observabilidade, Admin Dashboard, Automation (extensão de
`jobs/`/`workflows/` — não é módulo próprio, ver `ARCHITECTURE_FINAL.md`).

**Limites**: não implementa regra de negócio de nenhum módulo de
plataforma (CRM, portfólio, conteúdo editorial, etc.).

**Dependências permitidas**: nenhuma — Core não depende de nenhum
módulo de plataforma.

**Dependências proibidas**: qualquer pacote de módulo (`business/`,
`investments/`, `content_studio/`, `knowledge/`), em qualquer direção.

**Jobs**: publica/processa os handlers já existentes (`memory.embed`,
`contact.summarize`, `whatsapp.send_text`, `workflow.trigger`,
`whatsapp.process_inbound`) e roda o worker que processa os handlers
registrados por qualquer módulo — o worker descobre handlers por
convenção (`@job_handler(...)`), o mesmo princípio de auto-descoberta já
usado pelo Agent Registry, não um import estático de módulo dentro do
Core.

**APIs internas**: nenhuma exposta a módulos — Core é provedor de
infraestrutura, não consumidor.

**Ownership**: todas as tabelas hoje existentes (`contacts`, `messages`,
`users`, `tasks`, `calendar`, `notes`, `embeddings`, `jobs`, `logs`,
`refresh_tokens`, `email_accounts`, `google_*_accounts`, etc.), mais
`store_customers`/`church_members` até uma decisão de migração ser
executada (ver `ARCHITECTURE_FINAL.md`, "Classificação dos agentes").

---

## Business

**Objetivo**: CRM, pipeline comercial, follow-up, projetos e KPIs —
gerenciar clientes e o funil comercial de Dario.

**Responsabilidades**: cadastro e gestão de clientes, deals/pipeline,
agendamento de follow-up, projetos, KPIs comerciais; agente `crm_agent`
(sucessor de `store_agent` na migração planejada).

**Limites**: não decide nem gera conteúdo (delega a Content Studio via
job); não acessa dado de investimento; não substitui os contatos de
WhatsApp existentes (isolamento PROD-005) nem a agenda interna
(`/api/calendar`).

**Dependências permitidas**: Core (Orchestrator, Memory, fila de jobs,
Auth); Provider HubSpot via `providers/factory.py` próprio.

**Dependências proibidas**: leitura direta de tabela de Investments,
Content Studio ou Knowledge; leitura de `store_customers` sem a
migração de dado ser executada explicitamente (ainda não decidida em
nível de implementação).

**Jobs publicados**: `business.generate_proposal` (processado por
Content Studio), `business.generate_report`.

**Jobs consumidos**: nenhum de outro módulo na v1.

**Eventos publicados** (Event Bus, notificação — nunca carregam
obrigação): `business.client_profile_analyzed`,
`business.followup_scheduled`, `business.deal_stage_changed`.

**Eventos consumidos**: `content_studio.presentation_generated`
(atualiza UI/notifica — a obrigação de gerar a apresentação em si
já foi cumprida via job antes desse evento existir).

**APIs internas**: `/api/business/*` (CRUD deals/clients/followups);
serviço público `business.services.get_client_profile(client_id)` —
único ponto de leitura síncrona exposto a outros módulos.

**Ownership**: `clients`, `deals`, `followups`, `projects`, `kpis`.

---

## Investments

**Objetivo**: acompanhamento de carteira pessoal, cenário macro e
relatórios (Inside Diário). **Escopo v1 explicitamente pessoal — não
presta serviço a terceiros.**

**Responsabilidades**: registrar/consultar portfólios e holdings, gerar
cenário macro a partir de dados públicos, gerar relatórios.

**Limites**: não executa ordens ou operações de mercado (somente
leitura/relatório na v1); não presta aconselhamento a terceiros (risco
regulatório documentado em `docs/roadmap/ROADMAP_24_MONTHS.md`); não
acessa dado de cliente de Business.

**Dependências permitidas**: Core (fila de jobs, Memory para RAG de
relatórios anteriores); Providers de dados de mercado/macro (nenhum
conectado ainda — maior lacuna de integração da plataforma).

**Dependências proibidas**: leitura direta de Business, Content Studio
ou Knowledge; nunca gera o artefato final de conteúdo (PDF/carrossel/
vídeo) ele mesmo — publica job para Content Studio fazer isso.

**Jobs publicados**: `investments.generate_daily_report` (processado
por Content Studio).

**Jobs consumidos**: nenhum na v1.

**Eventos publicados**: `investments.macro_scenario_updated`.

**Eventos consumidos**: `knowledge.news_ingested` (gatilho leve/
opcional — a geração do relatório é acionada por job explícito, não
depende de o evento chegar).

**APIs internas**: `/api/investments/*`; serviço público
`investments.services.get_latest_scenario()`.

**Ownership**: `portfolios`, `holdings`, `funds`, `macro_scenarios`,
`reports`.

---

## Content Studio

**Objetivo**: produção de conteúdo (posts, PDFs, carrosséis, vídeos,
copywriting) para os canais de Dario.

**Responsabilidades**: gerar e agendar peças de conteúdo, publicar em
canais conectados, copywriting assistido por IA; agentes
`copywriter_agent` (sucessor de `content_agent`) e `designer_agent`.

**Limites**: não decide estratégia comercial (recebe contexto de
Business via payload de job, não o define); não é dono de dado de
cliente nem de investimento — todo dado de entrada chega pelo próprio
job que o disparou, nunca por leitura direta de tabela alheia.

**Dependências permitidas**: Core; Providers Canva, Adobe for
Creativity, Instagram, LinkedIn (via `providers/factory.py` próprio).

**Dependências proibidas**: leitura direta de tabela de Business ou
Investments.

**Jobs publicados**: nenhum — é majoritariamente processador, não
originador, de cadeias cross-módulo.

**Jobs consumidos/processados**: `business.generate_proposal`,
`investments.generate_daily_report`.

**Eventos publicados** (todos notificação — a entrega real acontece
dentro do processamento do job; o evento só avisa que aconteceu):
`content_studio.presentation_generated`, `content_studio.pdf_generated`,
`content_studio.carousel_generated`, `content_studio.video_generated`,
`content_studio.post_scheduled`, `content_studio.metrics_tracked`.

**Eventos consumidos**: nenhum — reage a jobs, não a eventos.

**APIs internas**: `/api/content-studio/*`.

**Ownership**: `content_pieces`, `channels`, `editorial_calendar`,
`drafts`.

---

## Knowledge

**Objetivo**: base de conhecimento e biblioteca de prompts,
complementar ao que o Memory Manager do Core já indexa (Google Drive).

**Responsabilidades**: metadado de fontes de conhecimento além do
Drive; biblioteca de prompts reutilizáveis.

**Limites**: não reimplementa busca semântica — delega 100% ao Memory
Manager do Core; não duplica embeddings/índice já existentes.

**Dependências permitidas**: Core, via serviço público do Memory
Manager (módulo dependendo de Core é sempre permitido).

**Dependências proibidas**: leitura direta da tabela `embeddings` fora
do Memory Manager; leitura de tabela de qualquer outro módulo de
plataforma.

**Jobs publicados**: `knowledge.ingest_source`.

**Jobs consumidos**: nenhum na v1.

**Eventos publicados**: `knowledge.news_ingested` (notificação — a
obrigação de reagir, se houver, é do módulo que escuta, não de
Knowledge garantir a entrega).

**Eventos consumidos**: nenhum.

**APIs internas**: `/api/knowledge/*`.

**Ownership**: `knowledge_sources`, `prompt_templates`.

---

## Não são módulos (classificação explícita)

| Nome | Classificação | Onde vive |
|---|---|---|
| **Automation** | Core | Extensão de `jobs/`/`workflows/` já existentes — zero tabela própria |
| **Research Lab** | Processo, não código | `docs/architecture/`, `docs/governance/`, `docs/modulos/`, `docs/roadmap/` — RFC/ADR em markdown+git |
| **Admin** | Core, já existente | Cresce de escopo para observar todos os módulos via `manifest.py`, não é módulo novo |

Estes três nomes continuavam na lista de "módulos" na versão anterior
(`docs/modulos/MODULE_CATALOG.md`) — reclassificados nesta consolidação
conforme `ARCHITECTURE_FINAL.md`.
