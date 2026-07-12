# ⚠️ DEPRECATED: Use ARCHITECTURE_FINAL.md (root) instead

**This document is superseded and no longer the authoritative source.**

Refer to the following documents in the repository root instead:
- `ARCHITECTURE_FINAL.md` — Consolidated platform architecture and vision (primary reference)
- `MODULE_CATALOG.md` — Module specifications and contracts
- `ARCHITECTURE_DECISIONS.md` — Architectural decisions and rationale
- `AI_GOVERNANCE.md` — AI roles and governance framework
- `ARCHITECTURE_MIGRATION_PLAN.md` — Phased migration plan

Content from this document has been consolidated into ARCHITECTURE_FINAL.md.

---

# Dario Platform — Master Context

Contexto arquitetural de referência para a Dario Platform. Este é o
documento a ler primeiro para entender o que a plataforma é, por que
existe, e o princípio que governa toda decisão futura. Para decisões
específicas já tomadas, ver `docs/architecture/ARCHITECT_DECISIONS.md`.
Para o catálogo de módulos, ver `docs/modulos/MODULE_CATALOG.md`.

**Este documento é planejamento — nenhum módulo aqui descrito foi
implementado.** Para o que já existe e está em produção, ver
`../architecture.md` (arquitetura do Core, inalterada por este
documento) e `PROJECT_STATUS.md` (na raiz do repositório).

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

Toda decisão de arquitetura futura se testa contra a mesma pergunta:
**"esta alteração aproxima ou afasta a Dario Platform da visão de longo
prazo?"** Se afastar, não implementa. Se aproximar, explica por quê antes
de começar — formalizado como critério de aceite de RFC em
`docs/architecture/MODULE_PATTERNS.md`.

## Decisão de topologia: monolito modular

Um backend deployável, um frontend deployável. Fronteiras impostas por
código e contrato, não por rede — não microsserviços.

**Justificativa**: dividir em microsserviços agora **afastaria** da
visão — multiplica containers, modos de falha de rede e coordenação de
deploy sem nenhum ganho real (não há time crescendo, não há necessidade
de escalar um módulo independente do outro, o operador é único). Um
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

## Referências

- `docs/architecture/ARCHITECT_DECISIONS.md` — decisões arquiteturais registradas, com justificativa e status
- `docs/modulos/MODULE_CATALOG.md` — árvore de diretórios, contrato de módulo, catálogo de eventos, mapa de dados
- `docs/roadmap/ROADMAP_24_MONTHS.md` — sequenciamento, riscos, oportunidades
- `MODULE_PATTERNS.md` — práticas de engenharia de produção para todo módulo novo
- `../architecture.md` — arquitetura do Core (Dario OS), inalterada
- `../../ROADMAP_v2.md` — roadmap do Core (v1.2.1 → v2.0.0)
- `../../CONTRIBUTING.md` — convenções de Agent/Tool/Provider que todo módulo reaplica
