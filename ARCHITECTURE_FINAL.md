# Dario Platform — Arquitetura Consolidada

Fonte única e definitiva da arquitetura da Dario Platform, resultado da
consolidação de `PLATFORM_ARCHITECTURE.md`, `ARCHITECTURE_REVIEW.md`,
`ARCHITECTURE_DECISIONS.md` e da árvore `docs/architecture/`,
`docs/modulos/`, `docs/roadmap/`, `docs/governance/`. Este documento
substitui `PLATFORM_ARCHITECTURE.md` como referência — o arquivo antigo
permanece no repositório por ora (nenhum documento foi apagado ou movido
nesta etapa) mas não deve mais ser editado como fonte.

Este é um documento de especificação. **Nada aqui foi implementado.**
Para o que já existe em produção, ver `docs/architecture.md` (Core,
inalterado) e `PROJECT_STATUS.md`.

## Visão

Centralizar toda a operação **profissional** de Dario Marques Neto em um
único ecossistema: trabalho, clientes, investimentos, inteligência
artificial, conteúdo, pesquisa, automações, documentos, conhecimento,
negócios e produtividade.

O Dario OS — tudo que existe hoje (Orchestrator, Agents, Memory, Event
Bus, Dashboard, Tool Registry, Providers) — é o **Core** da Dario
Platform: a infraestrutura compartilhada sobre a qual todo módulo novo é
construído.

## Princípio arquitetural central

A plataforma não precisa de uma arquitetura nova — precisa continuar
aplicando a que já existe, em mais domínios. O padrão de plugin já foi
provado 4 vezes no Core (WhatsApp Providers, LLM Providers, Google
Workspace, Admin Dashboard).

Toda decisão que toque fronteira entre Core e módulo, contrato de
comunicação entre módulos, ou modelo de dado compartilhado, responde
antes de ser tomada: **"esta alteração aproxima ou afasta a Dario
Platform da visão de longo prazo?"** Esta é a única formulação oficial
da pergunta — não repetida em nenhum outro documento além deste e de
`docs/architecture/MODULE_PATTERNS.md`, que a aplica operacionalmente.

## Topologia: monolito modular

Um backend deployável, um frontend deployável. Fronteiras impostas por
código e contrato, não por rede — não microsserviços. Microsserviços
agora afastariam da visão (custo operacional sem ganho real, dado
operador único e sem necessidade de escala independente por módulo); a
opção de extrair um módulo para serviço próprio no futuro continua
aberta, desde que a disciplina de fronteira abaixo seja seguida.

## Regra de dependência

**Core nunca importa de módulo. Módulo sempre pode importar de Core.**
`orchestrator/`, `agents/`, `events/`, `memory/`, `providers/`, `jobs/`
— nenhum pacote do Core referencia `business/`, `investments/`, ou
qualquer outro módulo de plataforma, em nenhuma linha.

## Como módulos se comunicam — 4 canais, não 3

Revisão desta etapa: a especificação anterior listava 3 canais e não
incluía a fila de jobs, apesar de fluxos de negócio obrigatórios
exigirem exatamente essa garantia. Canal correto, em ordem de uso:

1. **Fila de jobs do Core** (já existe: Postgres, durável, retry com
   backoff exponencial, claim atômico) — obrigatório para **qualquer
   transição de estado que, se perdida, deixa o sistema num estado
   inconsistente observável por um humano** (proposta nunca gerada,
   relatório nunca produzido, follow-up nunca agendado). Um módulo
   publica um job (`@job_handler("business.generate_proposal")`, mesmo
   padrão já usado hoje), outro módulo o processa.
2. **Event Bus** (fan-out best-effort via Redis) — **apenas para
   notificação onde perda é aceitável**: métricas, visibilidade no
   Admin, reações totalmente opcionais. Nunca carrega uma obrigação de
   negócio.
3. **Orchestrator/Agent** — quando a ação cruzada precisa ser síncrona
   dentro de um plano conversacional de um agente.
4. **Serviço público versionado do módulo** — último recurso, quando um
   módulo precisa de um dado síncrono de outro (ex.:
   `business.services.get_client_profile(client_id)`). Nunca acesso
   direto ao repositório/modelo ORM de outro módulo.

## Módulos da plataforma (revisado nesta consolidação)

Critério objetivo para "o que é módulo": **possui ao menos uma tabela de
dado genuinamente nova, que não pertence a nenhum domínio do Core.**
Quem não atende esse critério é Core, não módulo — ainda que more em um
pacote de código separado por organização.

| Nome | Classificação final | Por quê |
|---|---|---|
| **Business** | Módulo de plataforma | Tabelas novas (`clients`, `deals`, `followups`, `projects`, `kpis`) |
| **Investments** | Módulo de plataforma | Tabelas novas (`portfolios`, `holdings`, `funds`, `macro_scenarios`, `reports`) |
| **Content Studio** | Módulo de plataforma | Tabelas novas (`content_pieces`, `channels`, `editorial_calendar`, `drafts`) |
| **Knowledge** | Módulo de plataforma, deliberadamente mínimo | Tabelas novas (`knowledge_sources`, `prompt_templates`), mas a função central (busca) é 100% delegada ao Memory Manager do Core |
| **Automation** | **Core**, não módulo | Zero tabela própria — é extensão de `jobs/`/`workflows/` já existentes |
| **Research Lab** | **Processo**, não módulo, não código | RFC/ADR/benchmarks vivem em `docs/`; só vira código se markdown+git se mostrar insuficiente |
| **Admin** | **Core**, já existente | Cresce de escopo para observar todos os módulos, não é módulo novo |

Contagem oficial de módulos de plataforma a construir: **4** (Business,
Investments, Content Studio, Knowledge) — não 7, como o rascunho
original listava.

## Contrato formal de módulo

| Obrigação | Mecanismo |
|---|---|
| Rotas com prefixo próprio | `app.include_router(x_router, prefix="/api/business")` |
| Dono exclusivo dos seus modelos | Sem FK direta para tabela de outro módulo |
| Capacidade conversacional (se houver) | `agents/` + `tools/`, padrão `@register_agent`/`Tool(...)` |
| Integração externa | `providers/<nome>/provider.py`, implementa o marcador `PlatformProvider` do Core (ver "Providers" abaixo) |
| Comunicação com outro módulo | Um dos 4 canais acima, na ordem de preferência dada |
| Visibilidade no Admin | `manifest.py` com schema fixo: `{module, version, status, headline_metric}` — sem campos livres |

## Classificação definitiva dos agentes do Core

| Agente | Domínio | Classificação | Quando migra |
|---|---|---|---|
| `assistant` | Gateway WhatsApp + Google Workspace | Core, permanente | — |
| `personal` | Agenda/tarefas/notas internas | Core, permanente (produtividade pessoal, não "operação profissional" de terceiros) | — |
| `church` | Oração, escalas, membros | Core, permanente (comunitário/pastoral — fora dos 11 itens da Visão) | — |
| `store` | Produtos, pedidos, clientes | Migra para `business/agents/` | Quando Business v1 for construído |
| `content` | Conteúdo, pesquisa, documentos | Migra para `content_studio/agents/` | Quando Content Studio v1 for construído |

`store_customers` é o seed literal de `Client` em Business. `church_agent`
não migra para nenhum módulo — não é uma lacuna da taxonomia, é evidência
de que ela é escopada para domínios profissionais.

## Providers — governança

Toda integração externa nova é Strategy+Factory. Todo Provider de módulo
implementa um marcador mínimo compartilhado do Core — `PlatformProvider`
— tornando a disciplina estruturalmente verificável, não apenas social.

Integrações já disponíveis no ambiente de desenvolvimento: HubSpot
(Business), Adobe for Creativity/Canva/Figma/Gamma (Content Studio),
busca/leitura web (apoio a Research Lab). Investments não tem nenhuma
integração de dados de mercado conectada ainda.

## Dados

Um único Postgres, uma única história do Alembic, revisões prefixadas
por módulo, disciplina expand-contract obrigatória. Estratégia de
escala (read replica, particionamento) fica deliberadamente adiada até
haver evidência real de contenção — gatilho: p95 de latência perceptível
ou volume que torne o backup diário impraticável.

## Observabilidade

Métricas `darioos_<módulo>_*`. Correlation/Request ID por requisição
HTTP já existe. **Gap parcialmente mitigado nesta consolidação**: como
fluxos críticos agora passam pela fila de jobs (não mais Event Bus), o
rastreamento de um fluxo multi-etapa herda os IDs de job já existentes —
reduz, mas não elimina, a necessidade de um Flow ID dedicado para
correlacionar uma cadeia de jobs relacionados a um único processo de
negócio ponta a ponta. Segue como item aberto.

## Engenharia de produção

CI único enquanto couber no orçamento de tempo; suíte completa do Core
roda sempre. Testes de contrato entre Core e módulo. E2E sempre contra
build de produção, nunca `next dev`. Todo módulo novo nasce atrás de
feature flag (env-var). Rollback = reverter código + redeploy,
garantido pela disciplina expand-contract nas migrações.

## Roadmap

Ver `docs/roadmap/ROADMAP_24_MONTHS.md` para o sequenciamento completo
por trimestre, e `ARCHITECTURE_MIGRATION_PLAN.md` para as fases de
migração operacionais desta consolidação.

## Papéis de IA na plataforma

Ver `AI_GOVERNANCE.md` — formaliza quem decide visão/arquitetura/
implementação/pesquisa, e quem tem permissão de alterar o repositório
oficial.

## O que mudou nesta consolidação em relação ao rascunho original

1. Automation e Research Lab deixam de ser contados como módulos de
   plataforma (eram 7, agora são 4 módulos reais).
2. Canal de comunicação entre módulos ganha um 4º mecanismo (fila de
   jobs) para fluxos obrigatórios — o rascunho original só listava 3 e
   usava Event Bus (best-effort) para etapas que não podiam falhar
   silenciosamente.
3. Classificação dos 5 agentes do Core, incluindo `church_agent`,
   deixa de ser uma decisão pendente única e vira uma tabela definitiva
   por agente.
4. Este documento passa a ser a fonte única — antes havia duplicação
   completa entre `PLATFORM_ARCHITECTURE.md` e a árvore em `docs/`.

## Referências

- `MODULE_CATALOG.md` — detalhamento por módulo (objetivo, limites, dependências, eventos, ownership)
- `AI_GOVERNANCE.md` — papéis das IAs envolvidas no projeto
- `ARCHITECTURE_MIGRATION_PLAN.md` — fases de migração
- `docs/architecture.md` — arquitetura do Core (Dario OS), inalterada
- `ROADMAP_v2.md` — roadmap do Core (v1.2.1 → v2.0.0)
- `CONTRIBUTING.md` — convenções de Agent/Tool/Provider que todo módulo reaplica
- `ARCHITECTURE_REVIEW.md` / `ARCHITECTURE_DECISIONS.md` — histórico da revisão que originou esta consolidação (mantidos como registro, não como fonte corrente)
