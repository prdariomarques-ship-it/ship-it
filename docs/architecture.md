# Arquitetura do Dario OS

## Visão geral

O Dario OS é composto por 8 containers orquestrados pelo Docker Compose:

```mermaid
graph TB
    subgraph Edge
        Caddy["Caddy<br/>reverse proxy + TLS"]
    end

    subgraph App["Aplicação"]
        Frontend["Frontend<br/>Next.js"]
        Backend["Backend<br/>FastAPI"]
        N8N["n8n<br/>workflows"]
    end

    subgraph Infra["Infraestrutura"]
        Postgres[(PostgreSQL)]
        Redis[(Redis)]
        Qdrant[(Qdrant)]
        WA["WhatsApp<br/>provider"]
    end

    Caddy --> Frontend
    Caddy --> Backend
    Caddy --> N8N
    Backend <--> N8N
    Backend --> Postgres
    Backend --> Redis
    Backend --> Qdrant
    Backend --> WA
    WA --> WhatsAppNetwork(("WhatsApp"))
```

## Arquitetura interna do backend (Fase 3)

Três peças centrais consolidam a plataforma: o **Agent Registry** (quem existe), o **Tool Registry** (o que os agentes podem fazer) e o **AI Orchestrator** (como uma conversa é conduzida), com o **Event Bus** desacoplando quem produz um acontecimento de quem reage a ele.

```mermaid
graph TB
    subgraph Presentation["Apresentação"]
        ChatAPI["/api/chat"]
        AgentsAPI["/api/agents/*"]
        Webhook["/api/webhooks/whatsapp"]
    end

    subgraph Core["Núcleo cognitivo"]
        Orchestrator["AI Orchestrator<br/>seleciona agente, roda, publica eventos"]
        AgentRegistry["Agent Registry<br/>auto-discovery + @register_agent"]
        ToolRegistry["Tool Registry<br/>auto-registro no __post_init__"]
        BaseAgent["BaseAgent<br/>planner + executor + tools"]
        Planner["Planner"]
        Executor["AgentExecutor<br/>loop function calling"]
    end

    subgraph Memory["Memória"]
        MemoryManager["Memory Manager<br/>fachada única"]
        ShortTerm["curto prazo<br/>MessageRepository"]
        LongTerm["longo prazo<br/>Qdrant semantic search"]
        Knowledge["conhecimento<br/>Qdrant tag=knowledge"]
        Preferences["preferências<br/>Contact.preferences"]
    end

    subgraph Providers["Providers (Strategy + Factory)"]
        LLMFactory["LLM Factory"]
        LLMs["openai · anthropic · glm · gemini · ollama"]
        WAFactory["WhatsApp Factory"]
        WAProviders["openwa · baileys · evolution · official"]
    end

    subgraph Bus["Event Bus"]
        EventBus["pub/sub interno<br/>+ fan-out Redis best-effort"]
    end

    subgraph Jobs["Fila de jobs"]
        JobQueue["Postgres + worker<br/>retry exponencial"]
    end

    ChatAPI --> Orchestrator
    AgentsAPI --> Orchestrator
    Orchestrator --> AgentRegistry
    AgentRegistry --> BaseAgent
    BaseAgent --> Planner
    BaseAgent --> Executor
    Executor --> ToolRegistry
    Planner --> MemoryManager
    MemoryManager --> ShortTerm
    MemoryManager --> LongTerm
    MemoryManager --> Knowledge
    MemoryManager --> Preferences
    Executor --> LLMFactory
    LLMFactory --> LLMs
    Orchestrator -. publica .-> EventBus
    Webhook -. publica .-> EventBus
    JobQueue -. publica .-> EventBus
    Webhook --> JobQueue
    Webhook --> WAFactory
    WAFactory --> WAProviders
```

## Camadas (Clean Architecture)

| Camada | Diretórios | Responsabilidade |
| --- | --- | --- |
| Apresentação | `api/`, `*/router.py`, `webhooks/` | HTTP, validação Pydantic, status codes |
| Coordenação cognitiva | `orchestrator/`, `agents/registry.py`, `agents/tools/registry.py` | Seleção de agente, descoberta de agentes/ferramentas, eventos de ciclo de vida |
| Aplicação | `auth/service`, `chat/service`, `jobs/service`, `memory/manager`, `agents/base` | Casos de uso e orquestração |
| Domínio | `models/` | Entidades (SQLAlchemy 2, tipagem forte) |
| Acesso a dados | `repositories/` | Repository pattern; nenhuma query fora daqui ou da fábrica CRUD |
| Infraestrutura | `providers/`, `database/`, `memory/service`, `services/`, `jobs/worker`, `events/bus` | Vendors, banco, Redis, Qdrant, pub/sub |

### Padrões aplicados

- **Repository Pattern** — `SQLAlchemyRepository[T]` genérico + repositórios especializados (`ContactRepository.get_or_create_by_phone`, `JobRepository.due_jobs`, ...). Rotas e serviços não montam queries.
- **Dependency Injection** — `Depends(get_db)`, `Depends(get_auth_service)`, `CurrentUser`; os factories de provider são funções puras substituíveis em teste.
- **Factory Pattern** — `providers/llm/factory.py`, `providers/whatsapp/factory.py`: seleção por configuração, sem `if` espalhado.
- **Strategy Pattern** — contratos `LLMProvider` e `WhatsAppProvider`; cada vendor é uma estratégia intercambiável (inclusive normalização de webhook por provider).
- **Registry + auto-discovery** (novo na Fase 3) — `agents/registry.py` e `agents/tools/registry.py` substituem o dicionário manual: um decorator (`@register_agent`) ou a própria construção do objeto (`Tool.__post_init__`) é o registro; `pkgutil.iter_modules` importa todo `agents/*_agent.py` automaticamente. Nenhum arquivo central lista agentes ou ferramentas.
- **Facade Pattern** (novo na Fase 3) — `memory/manager.py` unifica curto prazo, longo prazo, conhecimento e preferências atrás de uma API; `orchestrator/service.py` unifica seleção de agente + execução + eventos.
- **Observer / Pub-Sub** (novo na Fase 3) — `events/bus.py`: publicar não sabe (nem precisa saber) quem está ouvindo.
- **Service Layer** — regras de negócio (rotação de refresh token, resumo de contato, enfileiramento) vivem em serviços, não em rotas.
- **Open/Closed** — novo agente = arquivo + decorator (zero edição em código existente); nova ferramenta = arquivo + import; novo provider = classe + entrada no factory; novo job = decorator `@job_handler`.

## AI Orchestrator

`orchestrator/service.py` é o único ponto de entrada para "rodar uma conversa com um agente". Chat (`/api/chat`), a execução direta (`/api/agents/{name}/run`) e o auto-reply do WhatsApp (`jobs/handlers.py::process_inbound_whatsapp_message`) delegam aqui em vez de chamar `agents.registry.get_agent` + `agent.run(...)` cada um à sua maneira (era assim antes da Fase 3 — chat/service.py duplicava a busca de memória que `BaseAgent.run` já fazia).

Responsabilidades hoje:
1. Seleciona o agente pelo nome (`UnknownAgentError` se inválido — traduzido para 404 pelas rotas).
2. Publica `agent.selected` no Event Bus.
3. Roda o agente **sob timeout** (`AGENT_RUN_TIMEOUT_SECONDS`, `asyncio.wait_for`) — um LLM travado ou um loop de tools não trava o chamador para sempre; excedido, publica `agent.failed` e levanta `AgentTimeoutError` (a fila de jobs trata isso como qualquer outra falha: retry com backoff, depois `FAILED`).
4. Registra métricas Prometheus (`darioos_agent_runs_total`, `_run_duration_seconds`, `_tool_calls_total`, `_tokens_total`, `_cost_usd_total`) — um único lugar, nenhum chamador precisa se instrumentar.
5. Publica `agent.replied` com contagem de tool calls, memórias usadas, tokens consumidos e custo estimado.

Deliberadamente não decide *como* o agente pensa (isso é `BaseAgent`/`Planner`/`AgentExecutor`) nem *qual* memória usar (isso é `MemoryManager`) — é uma camada fina de coordenação, não mais um lugar para lógica de negócio.

`AIOrchestrator.run` ganhou dois parâmetros opcionais na Fase 4.2 — `memories` e `history` — usados exclusivamente pelo Cognitive Pipeline (abaixo) para injetar um contexto já carregado uma única vez para todo o plano, em vez de cada etapa buscar memória de novo. Chamadores que não os passam (`/api/chat`, `/api/agents/{name}/run`) continuam com o comportamento de sempre: `BaseAgent.run` busca a própria memória.

O custo estimado usa uma tabela estática de preços por milhão de tokens (`providers/llm/base.py::estimate_cost_usd`) — aproximada por natureza (não substitui o faturamento real do provedor), mas suficiente como sinal operacional de custo por conversa/agente.

## Cognitive Pipeline (Fase 4.2)

A previsão da Fase 3 — "este método de seleção [de agente] cresce de nome explícito para um classificador de intenção" — se concretizou como o Cognitive Pipeline: o ponto de entrada para "uma mensagem chegou, pense antes de agir", usado pelo auto-reply do WhatsApp (`jobs/handlers.py::process_inbound_whatsapp_message`). Não é uma camada nova: é uma composição, dentro da camada de "Coordenação cognitiva" já existente (`orchestrator/`), de componentes pequenos e independentes — cada um testável isoladamente — que terminam delegando a execução real ao mesmo `AIOrchestrator.run` de sempre.

```mermaid
flowchart TD
    A[Mensagem recebida] --> B[Normalizar]
    B --> C["Intent Engine\n(orchestrator/intent.py)"]
    C --> D["Priority Engine\n(orchestrator/priority.py)"]
    D --> E["Carregar contexto\ncurto prazo + preferências + resumo"]
    E --> F{"Contexto profundo\nnecessário?"}
    F -- sim --> G["Memória longo prazo\n(Qdrant)"]
    G --> H{"Intenção pede\nconhecimento?"}
    H -- sim --> I["Conhecimento\n(Qdrant, source=knowledge)"]
    H -- não --> J
    I --> J["Cognitive Planner\n(orchestrator/planning.py)"]
    F -- não --> J
    J --> K{"needs_confirmation?"}
    K -- sim --> L["Responder pedindo confirmação\n(nenhuma etapa executada)"]
    K -- não --> M["Para cada etapa do Plano"]
    M --> N["Escolher agente\n(Agent Registry)"]
    N --> O["AI Orchestrator.run\n(agente + memória + tools)"]
    O --> P["Escolher e executar ferramentas\n(Tool Registry, dentro do AgentExecutor)"]
    P --> Q["Response Validator"]
    Q -- inválido, 1ª tentativa --> O
    Q -- ok ou 2ª tentativa --> R["Compor resposta final"]
    R --> S["Learning Engine\natualiza memória (categorias)"]
    S --> T["Registrar métricas + log estruturado"]
    T --> U[Responder ao usuário]
```

Cada etapa é um módulo independente em `orchestrator/`, sem estado compartilhado além do que passa explicitamente entre eles:

| Etapa | Módulo | Decisão primária | Caminho de degradação |
| --- | --- | --- | --- |
| Intenção | `intent.py::IntentEngine` | Function calling (`classify_intent`) — pode devolver várias hipóteses com confiança quando a mensagem é ambígua | Heurística por palavras-chave, só quando o modelo não responde ou levanta exceção |
| Prioridade | `priority.py::PriorityEngine` | Function calling (`classify_priority`), considerando a intenção já identificada | Mesma heurística, exposta também como `quick_priority_hint` (síncrona, sem LLM) para o webhook decidir a ordem de execução na fila sem esperar um modelo |
| Planejamento | `planning.py::CognitivePlanner` | Function calling (`create_plan`) — decide 1..5 etapas, o agente de cada uma (lido do Agent Registry, então um agente novo instalado por pasta já é planejável) e se precisa de confirmação | Plano de uma etapa só, com a mensagem original, agente escolhido por uma tabela pequena intenção→agente, caindo para `assistant` |
| Validação | `validation.py::ResponseValidator` | Determinística (sem LLM): resposta vazia, erro de ferramenta vazado na resposta, ferramenta que falhou | — (é ela própria o mecanismo, não tem fallback) |
| Aprendizado | `learning.py::LearningEngine` | Marca o contato com os domínios (`Contact.categories`) que os agentes usados no plano atendem, deduplicado na escrita | — |

Nenhum desses componentes chama uma ferramenta diretamente — Planner e Pipeline só decidem o quê e quem; a seleção e execução de ferramentas continuam exclusivamente dentro do `AgentExecutor`, através do Tool Registry, exatamente como antes da Fase 4.2.

### Fluxo do Planner

`CognitivePlanner.create_plan` é o mesmo padrão de decisão-com-degradação dos outros dois engines, aplicado a "quantas etapas, com qual agente, precisa de confirmação":

```mermaid
flowchart TD
    A["create_plan(mensagem, intenção, prioridade)"] --> B["agent_names = Agent Registry.list_agents()\n(lido em tempo de execução — um agente novo\ninstalado por pasta já entra aqui sozinho)"]
    B --> C["LLM.chat(system + mensagem, tools=[create_plan])"]
    C -->|"exceção (provider fora do ar)"| F["Plano de 1 etapa:\nobjective=mensagem original\nagent = tabela intenção→agente, senão assistant"]
    C -->|"sem tool_call\n(stub/degradado)"| F
    C -->|"tool_call create_plan"| D["Para cada etapa recebida (máx. 5):\nagente válido no Registry?"]
    D -->|não| E["substitui pelo agente da tabela\nintenção→agente, senão assistant"]
    D -->|sim| G[mantém o agente escolhido]
    E --> H["Plan(steps, needs_confirmation, reasoning)"]
    G --> H
    F --> H
```

O Planner nunca inventa um agente que não existe: um nome desconhecido vindo do modelo (alucinação, ou um agente removido depois do treinamento do prompt) é substituído, nunca aceito como está — a mesma tabela pequena intenção→agente que serve de fallback quando não há resposta estruturada nenhuma.

**"Pensar antes de agir" tem um limite bem definido, de propósito**: no máximo 2 tentativas de validação por etapa (`_MAX_VALIDATION_ATTEMPTS`), no máximo 5 etapas por plano (`_MAX_PLAN_STEPS`), e nenhuma etapa dependente roda se sua dependência falhou (fica `SKIPPED`). Um plano nunca fica girando indefinidamente, e a resposta final nunca fica em silêncio — mesmo esgotando as tentativas, a melhor resposta disponível é devolvida (ver `docs/fase4.2-relatorio.md` para os testes que provam isso).

**Troca automática de provider**: uma novidade que mora em `agents/executor.py`, não no pipeline — `AgentExecutor` agora captura qualquer exceção levantada pelo provider LLM configurado (diferente de um provider que degrada normalmente para `STUB_REPLY`, que nunca levanta) e tenta uma vez com `LLM_FALLBACK_PROVIDER`, se configurado. Sem fallback configurado (o padrão), o comportamento é idêntico ao pré-Fase-4.2: a exceção propaga. Como todo agente passa pelo `AgentExecutor`, essa troca beneficia qualquer chamador (chat, `/api/agents/*/run`, Cognitive Pipeline), não só o WhatsApp.

**Prioridade de execução real, não só classificada**: o webhook usa `quick_priority_hint` (sem LLM, seguro para o hot path) para decidir `scheduled_at` do job `whatsapp.process_inbound` — mensagens não-urgentes mantêm `delay_seconds=0` (comportamento idêntico ao pré-Fase-4.2); mensagens urgentes são agendadas alguns segundos no passado, o que as torna imediatamente devidas **e** as ordena à frente de jobs já na fila (`JobRepository.due_jobs` ordena por `scheduled_at` crescente). O `PriorityEngine` completo (com LLM) roda de qualquer forma dentro do pipeline, mas seu resultado não pode mais alterar a ordem de um job que já foi retirado da fila — só afeta como a conversa é tratada dali em diante (profundidade de contexto, aprendizado).

## Agent Registry e Tool Registry (arquitetura de plugin)

Instalar um agente novo é **só criar o arquivo**:

```python
# agents/weather_agent.py
@register_agent
class WeatherAgent(BaseAgent):
    ...
```

`agents/registry.py` importa automaticamente qualquer `agents/*_agent.py` (via `pkgutil.iter_modules`, executado uma vez, de forma preguiçosa, na primeira chamada a `get_agent`/`list_agents`) — o decorator roda no import e o agente já está disponível em `GET /api/agents`, `/api/chat` e `/api/agents/{name}/run`. Nenhum dicionário central para editar.

Ferramentas seguem o mesmo princípio, de forma ainda mais direta: `Tool` é um dataclass cujo `__post_init__` se registra sozinho no Tool Registry — a própria construção do objeto módulo-nível (`create_task_tool = Tool(...)`) é o registro. `GET /api/agents/tools` lista todas as ferramentas do sistema, de qualquer agente, para descoberta (base para o futuro AI Console).

### Fluxo de ferramentas

O Planner (cognitivo ou de agente) nunca chama uma ferramenta — só o `AgentExecutor` o faz, e só com ferramentas que o próprio agente declarou (`agent.tools`), cada uma já auto-registrada no Tool Registry:

```mermaid
sequenceDiagram
    participant Ex as AgentExecutor
    participant LLM as LLM Provider
    participant TR as Tool Registry
    participant T as Tool.run
    participant App as Serviço/Repositório

    Ex->>LLM: chat(mensagens, tools=specs)
    LLM-->>Ex: tool_calls (nome + argumentos)
    loop cada tool_call
        Ex->>TR: busca a Tool pelo nome (dict local, populado no __post_init__)
        Ex->>T: run(ToolContext(db, user), argumentos)
        T->>App: executa a regra de negócio real
        App-->>T: resultado
        T-->>Ex: JSON ("ok" ou "error")
        Ex->>Ex: registra ExecutedStep (tool, args, resultado,\nduração, status, reason)
    end
    Ex->>LLM: chat(mensagens + resultados das tools)
    LLM-->>Ex: resposta final (sem mais tool_calls)
```

Cada `ExecutedStep` carrega `status` (`"ok"`/`"error"`, derivado do envelope JSON da própria tool — `agents.executor.is_tool_error`) e `reason` (o texto que o modelo deu junto com a chamada da ferramenta, quando deu algum) — a auditabilidade que a Fase 4.2 pediu ("motivo da escolha, tempo, resultado, falhas") sem exigir que nenhuma das ~20 ferramentas existentes mudasse de assinatura.

## Event Bus

`events/bus.py` é um pub/sub assíncrono com dois destinos por publicação:
- **In-process**: assinantes (`event_bus.subscribe(nome, handler)`) rodam na mesma instância, sem serialização — é assim que módulos reagem a algo sem se importarem.
- **Redis (best-effort)**: a mesma publicação é replicada no canal `darioos:events` para outros processos (um worker dedicado futuro, o AI Console, uma métrica externa). Degrada silenciosamente se o Redis estiver fora; o caminho in-process nunca depende dele.

Não substitui a fila de jobs: eventos são *fire-and-forget* (sem retry, sem persistência garantida — use para notificação); qualquer coisa que precise sobreviver a uma queda do processo é um job, não um handler de evento.

Eventos publicados hoje: `whatsapp.message_received` (webhook), `agent.selected` / `agent.replied` / `agent.failed` (orchestrator), `job.started` / `job.succeeded` / `job.retry_scheduled` / `job.failed` (worker — migrado do antigo publisher Redis-only para o bus compartilhado, mesmo comportamento observável; o payload inclui `job_payload`, o payload original do job, para quem precisa agir sobre *o quê* falhou).

**Uso real na Fase 4.1**: o auto-reply do WhatsApp (`whatsapp.process_inbound`) é um job como qualquer outro — se esgotar as tentativas, o worker publica `job.failed`. Um subscriber registrado em `jobs/handlers.py::register_event_subscribers` (chamado explicitamente no startup, não como efeito colateral de import — importante para isolamento em testes, já que o reset de assinaturas entre testes derrubaria uma inscrição feita apenas na importação do módulo) reage a esse evento e enfileira uma mensagem de desculpas para o contato. Isso é o Event Bus fazendo trabalho real: o worker de jobs não conhece esse subscriber, e o subscriber não conhece o webhook — ambos só conversam através do evento.

## Memory Manager

`memory/manager.py` é a fachada única que qualquer agente ou serviço usa para memória — compõe peças já existentes e testadas, não as reimplementa:

| Tipo | Método | Implementação |
| --- | --- | --- |
| Curto prazo | `short_term(contact_id)` | `MessageRepository.recent_for_contact` (Postgres) |
| Longo prazo | `long_term_search(query, contact_id)` | Busca semântica no Qdrant (`MemoryService`) |
| Conhecimento | `knowledge_search(query)` | Mesma coleção Qdrant, filtrada por `source="knowledge"` — consultada de verdade pela primeira vez na Fase 4.2, pelo Cognitive Pipeline |
| Preferências | `get_preferences` / `set_preference` | `Contact.preferences` (JSON) — a tool `update_contact_preference` já usa este caminho |
| Resumo | `get_summary` (Fase 4.2) | `Contact.summary`, mantido por `ContactMemoryService.summarize_contact` |
| Categorias/padrões | `add_categories` (Fase 4.2) | `Contact.categories` (JSON); deduplica na escrita — nunca grava a mesma categoria duas vezes |

`BaseAgent.run` chama `memory_manager.build_agent_context(...)` (que por sua vez delega ao já existente `ContactMemoryService.build_context`) para montar o contexto do planner quando ninguém forneceu memória pronta — um único ponto de entrada em vez de cada chamador saber que a busca semântica vive em `memory/service.py`.

### Fluxo de memória (Fase 4.2)

O Cognitive Pipeline é o primeiro chamador a consultar **todos** os tipos de memória antes de responder, e o único a escrever de volta (aprendizado). Contexto caro (busca semântica) só é buscado quando a mensagem realmente precisa — evitar carregar contexto desnecessário é uma decisão explícita, não um efeito colateral:

```mermaid
flowchart LR
    subgraph Leitura["Carregar contexto (por mensagem)"]
        ST["short_term\n(sempre, se houver contact_id)"]
        PR["preferences\n(sempre, se houver contact_id)"]
        SU["summary\n(sempre, se houver contact_id)"]
        LT["long_term_search\n(só se prioridade alta/urgente\nou intenção não-trivial)"]
        KN["knowledge_search\n(só se a intenção pedir\nconhecimento/pesquisa)"]
    end

    ST --> HIST["history (ChatMessage[])"]
    PR --> MEM["memories (list[dict])"]
    SU --> MEM
    LT --> MEM
    KN --> MEM

    HIST --> ORCH["AIOrchestrator.run(history=, memories=)"]
    MEM --> ORCH
    ORCH --> AGENT["BaseAgent.run\n(pula o auto-fetch: memória já veio pronta)"]
    AGENT --> PLANNER["agents.planner.Planner.build_messages\n(system prompt + memórias + histórico + mensagem)"]

    subgraph Escrita["Atualizar memória (após responder)"]
        EMB["memory.embed (job)\nmensagem inbound/outbound"]
        SUMJOB["contact.summarize (job)\na cada N mensagens"]
        CAT["LearningEngine.add_categories\ndeduplicado"]
    end

    PLANNER -.-> EMB
    PLANNER -.-> SUMJOB
    PLANNER -.-> CAT
```

Toda busca semântica (Qdrant indisponível é um cenário real, não hipotético — já aconteceu em testes) é protegida por `try/except`: uma falha aí é registrada e ignorada, nunca derruba o pipeline inteiro. O mesmo vale para o auto-fetch original em `BaseAgent.run` — o padrão já existia desde a Fase 3, o Cognitive Pipeline só o reaplica no seu próprio ponto de leitura.

## Providers

```
providers/
  llm/        base.py (LLMProvider, ChatMessage, ToolSpec, LLMResult)
    openai/     chat completions + tools + embeddings
    anthropic/  messages API + tool_use (sem embeddings — EmbeddingsNotSupportedError)
    glm/        endpoint OpenAI-compatível da Zhipu (reaproveita OpenAIProvider por herança)
    gemini/     REST direto via httpx — sem SDK novo; function calling + embeddings próprios
    ollama/     endpoint OpenAI-compatível local (reaproveita OpenAIProvider por herança)
  whatsapp/   base.py (WhatsAppProvider, InboundMessage, ConnectionEvent, DeliveryAck)
    openwa/     wa-automate easy-api
    evolution/  Evolution API (message/sendText etc.)
    baileys/    gateway REST sobre a lib Baileys
    official/   WhatsApp Cloud API (Meta Graph)
  mail/       base.py (MailProvider, EmailMessage, EmailThread, EmailSearchQuery, OAuthTokens)
    gmail/      REST via httpx puro — OAuth 2.0 + Gmail API, somente leitura (Sprint 1)
```

`LLM_PROVIDER` e `EMBEDDING_PROVIDER` são independentes porque nem todo vendor tem API de embeddings de dimensão previsível (Anthropic não tem API de embeddings; GLM e Ollama têm, mas com dimensão que não bate com a coleção Qdrant configurada — ambos levantam `EmbeddingsNotSupportedError` de propósito em vez de gravar vetores incompatíveis silenciosamente). Sem chave/endereço configurado, todo provider degrada para resposta stub — o sistema continua de pé.

### WhatsApp Provider: contrato, confiabilidade e como adicionar um novo

Ver **`providers/whatsapp/README.md`** para o guia completo (contrato,
exemplo mínimo, checklist de testes). Resumo arquitetural:

- **Só tradução e transporte.** Um Provider nunca acessa banco, nunca
  enfileira job, nunca publica no Event Bus, nunca conhece regra de negócio —
  ele só converte o payload cru do gateway para um dos três modelos internos
  únicos (`InboundMessage`, `ConnectionEvent`, `DeliveryAck`) e envia mensagens
  através da interface padronizada. Depois dessa tradução, nenhum outro
  componente do sistema (webhook route, jobs, Memory Manager, AI Orchestrator)
  sabe qual gateway está configurado.
- **`WhatsAppProvider._request`** é o único caminho para chamadas HTTP ao
  gateway: dá retry com backoff exponencial, métricas de disponibilidade
  (`darioos_whatsapp_provider_requests_total{provider,status}`) e tradução de
  erro uniforme para os 4 providers de graça (nenhum duplica essa lógica). Um
  `max_attempts` override permite chamadas single-shot (usado por
  `health_check`, que não pode bloquear um readiness probe atrás de um
  gateway fora do ar).
- **Sessão e reconexão**: `parse_connection_event` normaliza mudanças de
  estado da sessão do gateway (`CONNECTED`/`AUTH_EXPIRED`/`RECONNECTING`/...).
  Uma sessão deslogada em um gateway baseado em WhatsApp Web genuinamente
  exige um humano re-escaneando o QR code — o sistema não finge uma
  reconexão automática que a tecnologia não oferece; em vez disso, registra o
  evento (log + métrica `darioos_whatsapp_session_status{provider}` + Event
  Bus `whatsapp.session_changed`) e, em `AUTH_EXPIRED`, emite um log de erro
  claro pedindo a intervenção.
- **Confirmação de entrega**: `parse_delivery_ack` normaliza acks de
  entrega/leitura quando o gateway suporta; o webhook atualiza
  `Message.delivery_status` e publica `whatsapp.message_delivery_ack`.
- **Ordem de mensagens**: `InboundMessage.timestamp` carrega a hora do evento
  reportada pelo próprio gateway; `MessageRepository.recent_for_contact`
  ordena por esse campo (com fallback para a ordem de chegada quando ausente),
  então uma redelivery de webhook fora de ordem não bagunça o histórico de
  conversa nem o contexto do agente.
- **Testes de compatibilidade** (`tests/test_whatsapp_provider_compatibility.py`,
  36+ casos): uma bateria parametrizada roda os mesmos testes de contrato
  contra os 4 providers registrados (nunca lançar exceção com payload
  malformado, `verify_signature`/`health_check` sempre devolvem `bool`, os 5
  métodos de envio existem, o provider está registrado na factory pelo seu
  próprio nome) — mais um `_FakeProvider` inédito, registrado só no teste, que
  prova concretamente a regra central: a rota de webhook e o envio funcionam
  através dele sem alterar uma linha de `webhooks/router.py` ou
  `api/whatsapp.py`. Essa suíte encontrou e corrigiu 3 bugs reais de robustez
  (OpenWA/Baileys/Evolution derrubavam com `AttributeError` ao receber
  `{"data": null}` — um payload malformado plausível de um gateway real).

Gemini foi implementado com `httpx` puro (já era dependência, usada pelos providers de WhatsApp) em vez do SDK oficial do Google — zero dependência nova. A única particularidade de tradução: Gemini não dá um `id` para cada chamada de função (diferente de OpenAI/Anthropic), então o provider sintetiza um id e mantém um mapa local `id → nome` ao converter a conversa, para devolver o resultado da ferramenta no formato `functionResponse` correto.

## Email (Gmail) — Sprint 1

Domínio novo e deliberadamente isolado, com o mesmo padrão Strategy + Factory dos providers acima (`providers/mail/`), mas sem reaproveitar `LLMProvider`/`WhatsAppProvider` — a forma de um mailbox (OAuth, threads, mensagens) não tem nada em comum com chat ou mensageria instantânea. Guia completo (arquitetura, isolamento, setup OAuth passo a passo): **[`docs/EMAIL.md`](EMAIL.md)**.

```mermaid
flowchart TB
    subgraph Gateway["Único gateway: assistant"]
        Tools["agents/tools/mail.py\n(4 tools, function calling)"]
    end
    Others["personal / church / store / content\n(sem tools de e-mail)"]
    Planner["Cognitive Planner"]
    Access["_get_access_token(context)\nresolve SEMPRE por context.user.id"]
    Repo["EmailAccountRepository"]
    Crypto["token_crypto\n(Fernet, EMAIL_TOKEN_ENCRYPTION_KEY)"]
    Provider["GmailProvider\n(httpx puro, escopo gmail.readonly)"]
    Google[(Gmail API)]

    Others -. "precisa de e-mail?" .-> Planner
    Planner -- "roteia a etapa para" --> Tools
    Tools --> Access
    Access --> Repo
    Access --> Crypto
    Access --> Provider
    Provider --> Google
```

- **Gateway único**: só `agents/assistant_agent.py` lista as quatro tools de e-mail. Um agente especializado que precise de contexto de e-mail não ganha acesso direto — a etapa correspondente do plano do Cognitive Planner é roteada para `assistant`, o mesmo mecanismo multi-etapa já existente (`orchestrator/planning.py`), sem nenhum canal novo de comunicação entre agentes.
- **Autorização em código, não no prompt** (mesmo princípio do PROD-005 para contatos do WhatsApp — ver `SECURITY.md`): `_get_access_token` resolve o mailbox estritamente a partir de `ToolContext.user.id`; nenhuma tool de e-mail tem um parâmetro de usuário/mailbox no schema.
- **Credenciais nunca em texto puro**: o refresh token OAuth é cifrado em repouso com Fernet antes de tocar o banco (`services/token_crypto.py`).
- **Somente leitura**: escopo `gmail.readonly` solicitado ao Google — enviar/responder/mover/excluir não existem em nenhum ponto do código desta sprint.
- **`mail/router.py`** expõe conexão/desconexão admin-only (`/api/mail/connect|status|disconnect`) e o callback OAuth (`/api/mail/oauth/callback`, autenticado por um `state` JWT de curta duração em vez de Bearer, porque é o Google — não o usuário — quem chama essa rota).

## Agentes

Um agente é composto por:

- **system prompt** — identidade e regras;
- **tools** — `Tool` = JSON Schema + handler async com `ToolContext(db, user)`; resultados voltam ao modelo como JSON;
- **memory** — `MemoryManager.build_agent_context` injeta memórias relevantes no contexto pelo planner;
- **planner** (`agents/planner.py`) — monta a lista de mensagens (prompt + memórias + histórico + pedido);
- **executor** (`agents/executor.py`) — loop de function calling: modelo → tool calls → resultados → ... até resposta final ou orçamento de iterações (`AGENT_MAX_ITERATIONS`), com troca automática de provider (`LLM_FALLBACK_PROVIDER`) se o provider configurado levantar uma exceção.

O executor registra cada passo (`steps` na resposta da API) e quantas memórias foram usadas (`AgentResult.memories_used`), o que dá auditabilidade às ações dos agentes sem que o chamador precise recalcular nada.

`Planner.build_messages` sempre teve um parâmetro `history` — só nunca tinha sido conectado a nada. A Fase 4.2 fechou essa lacuna: `BaseAgent.run` agora aceita `history` e repassa para o planner; `AIOrchestrator.run` aceita `history`/`memories` e repassa para `BaseAgent.run`. O Cognitive Pipeline é quem preenche os dois (curto prazo vira `history`; longo prazo + conhecimento + preferências + resumo viram `memories`) — chamadores que não passam nada continuam exatamente como antes.

### Fluxo de agentes

```mermaid
flowchart TD
    A["ai_orchestrator.run(agent_name, message, ...)"] --> B["Agent Registry: get_agent(agent_name)"]
    B -->|"nome desconhecido"| C[UnknownAgentError]
    B -->|encontrado| D["BaseAgent.run"]
    D --> E{"memories/history\njá fornecidos?"}
    E -- não --> F["MemoryManager.build_agent_context\n(auto-fetch, best-effort)"]
    E -- sim --> G["usa o que foi passado\n(pulo o auto-fetch)"]
    F --> H["Planner.build_messages\n(system prompt + memórias + histórico + mensagem)"]
    G --> H
    H --> I["AgentExecutor.run\n(function calling + Tool Registry)"]
    I --> J["AgentResult\n(reply, steps, usage, memories_used, duration_ms)"]
    J --> K["Event Bus: agent.replied\n+ métricas Prometheus"]
```

## Memória por contato

1. Toda mensagem (entrada/saída) é enfileirada como job `memory.embed` (fora do hot path da requisição) e vira embedding no Qdrant (`payload: content, source, contact_id`) com metadados auditáveis na tabela `embeddings`.
2. `last_interaction_at` é atualizado a cada interação.
3. A cada `CONTACT_SUMMARY_EVERY_N_MESSAGES` mensagens, o job `contact.summarize` pede ao LLM um resumo do histórico recente e grava em `contacts.summary`.
4. Agentes recebem memórias relevantes via `MemoryManager.long_term_search` (filtrável por contato) e podem gravar novas com a tool `store_memory`, ou preferências estruturadas com `update_contact_preference`.

## Fluxo ponta a ponta do WhatsApp (Fase 4.1)

Ver o diagrama de sequência completo no [README](../README.md#fluxo-de-execução-whatsapp--ponta-a-ponta-automático). Pontos de arquitetura que valem detalhar aqui:

- **`services/messaging.py::persist_outbound_message`** é o único lugar que persiste uma mensagem de saída e alimenta a memória do contato — usado tanto por `api/whatsapp.py` (envio manual via dashboard) quanto pelo job `whatsapp.send_text` (envio automático, seja pela resposta do agente ou por uma tool `send_whatsapp_message`). Antes da Fase 4.1, só o caminho da API fazia isso — o envio via fila silenciosamente pulava persistência e memória; extrair a função fechou essa lacuna nos dois lugares de uma vez.
- **`whatsapp.process_inbound`** (`jobs/handlers.py`) é o job que roda o Cognitive Pipeline (Fase 4.2; antes, chamava o AI Orchestrator diretamente para o agente fixo `assistant`) agindo em nome do **primeiro usuário admin** (`UserRepository.get_first_admin`) — Dario OS é um sistema de dono único, então ações de ferramentas disparadas por uma mensagem de WhatsApp (criar tarefa, agendar evento) pertencem ao dono da instância, não ao contato que escreveu.
- **Deduplicação**: o webhook verifica `external_id` antes de processar (uma redelivery do provider não gera nem resposta duplicada, nem embedding duplicado, nem job duplicado); uma constraint única em `messages.external_id` cobre a corrida entre requisições concorrentes (mesmo padrão de recuperação de `IntegrityError` já usado em `ContactRepository.get_or_create_by_phone`).
- **Assinatura do webhook**: `WhatsAppProvider.verify_signature(raw_body, headers)` (novo método na Strategy, com default no-op) permite que cada provider valide seu próprio esquema — `OfficialProvider` implementa HMAC-SHA256 real (`X-Hub-Signature-256`, o esquema da Meta); os demais seguem cobertos pelo `WEBHOOK_SECRET` compartilhado.
- **Loop/flood**: `RateLimiter.is_allowed` ganhou parâmetros opcionais de limite/janela (retrocompatível — sem eles, usa o limite HTTP global) para servir também como o freio de auto-reply por contato, sem duplicar lógica de rate limiting.
- **Nunca fica em silêncio**: se `whatsapp.process_inbound` esgota as tentativas, o Event Bus (`job.failed`) aciona uma mensagem de desculpas — ver seção Event Bus acima.

## Fila de jobs

- Tabela `jobs` (durável) + worker assíncrono iniciado no lifespan da API.
- Claim atômico com `SELECT ... FOR UPDATE SKIP LOCKED`: múltiplas réplicas do worker nunca processam o mesmo job duas vezes.
- `scheduled_at` permite agendamento; retry com backoff exponencial (`JOBS_RETRY_BACKOFF_SECONDS * 2^tentativa`) até `max_attempts`, depois `failed` com `last_error`; jobs órfãos (`RUNNING` após crash) são recuperados a cada tick.
- Eventos de ciclo de vida (`job.started`/`succeeded`/`retry_scheduled`/`failed`) são publicados no Event Bus (fan-out em `darioos:events`) e sempre persistidos em `logs`, mesmo sem assinantes.
- Por ser Postgres-backed, workers adicionais podem rodar em containers separados sem mudar o lado que enfileira.
- **Correção de robustez (Fase 4.1)**: quando um lote de jobs devidos inclui mais de um job (comum no fluxo do WhatsApp: `memory.embed`, `workflow.trigger` e `whatsapp.process_inbound` ficam devidos juntos), a falha de um job antigo `session.rollback()`ava a sessão compartilhada e expirava os objetos dos jobs seguintes do MESMO lote — o próximo acesso a um atributo (ex: `job.id` ao publicar o evento `started`) tentava um refresh implícito fora de um contexto async válido e derrubava com `MissingGreenlet`. `run_once()` agora captura os ids do lote antes de qualquer execução e re-busca cada job explicitamente (`repository.get(job_id)`, uma consulta segura e aguardada) antes de rodá-lo — nenhum job do lote fica vulnerável ao rollback de outro.

## Autenticação e permissões

- Access token JWT curto (30 min) + refresh token rotativo de 30 dias.
- Refresh tokens armazenados como hash SHA-256; rotação revoga o anterior; reuso de token revogado é rejeitado (mitiga replay); expirados são purgados a cada novo login.
- RBAC: papel `admin` (primeiro usuário) e `user`; `require_roles(...)` protege rotas administrativas (`/api/logs`, `/api/jobs`).
- `WEBHOOK_SECRET` (opcional): quando definido, `/api/webhooks/whatsapp` exige `X-Webhook-Token`.

## Migrações

Alembic com `env.py` async lendo `DATABASE_URL` das settings. O container do backend executa `alembic upgrade head` antes do uvicorn. Autogenerate: `alembic revision --autogenerate -m "..."`.

## Observabilidade

- **Liveness** `/health`, **readiness** `/health/ready` (Postgres obrigatório; Redis/Qdrant/WhatsApp marcam `degraded` — um gateway de WhatsApp fora do ar não derruba a API).
- **Métricas** `/metrics` (Prometheus): HTTP (`darioos_http_requests_total`/`_duration_seconds`), agentes (`darioos_agent_runs_total{agent,provider,status}`, `_run_duration_seconds`, `_tool_calls_total`, `_tokens_total`, `_cost_usd_total`), jobs (`darioos_job_duration_seconds{name}`) e WhatsApp (`darioos_whatsapp_provider_requests_total{provider,status}`, `darioos_whatsapp_session_status{provider}`) — todas com o template da rota/nome, não a URL/id bruto, para manter a cardinalidade baixa; probes isentos de rate limit.
- **Tempo por etapa**: cada chamada de ferramenta (`ExecutedStep.duration_ms`) e cada execução de agente (`AgentResult.duration_ms`) carregam sua própria medição, visível na resposta da API sem precisar consultar o Prometheus.
- **Logs estruturados** em JSON (`LOG_JSON=true`), um objeto por linha, prontos para Loki/ELK.
- **Auditoria** na tabela `logs` (webhooks, eventos de jobs) e no Event Bus (`agent.selected`/`agent.replied`/`agent.failed`, base para o futuro AI Console).

## Decisões e trade-offs

- Worker de jobs no mesmo processo da API por padrão (simplicidade); a fila durável e o claim atômico já permitem extrair para container dedicado quando a carga justificar, sem mudar nenhum código de enfileiramento.
- O webhook do WhatsApp é público por necessidade; proteja-o na borda (rede Docker/Caddy, `WEBHOOK_SECRET`, `OFFICIAL_APP_SECRET`) e prefira providers com autenticação de webhook.
- O provider Baileys pressupõe um gateway REST na frente da lib Node; o layout de endpoints é configurável via `BAILEYS_BASE_URL`.
- O Event Bus é aditivo: a maior parte dos fluxos ainda é chamada direta (síncrona) por decisão — reescrever tudo para "só eventos" trocaria simplicidade e rastreabilidade por um desacoplamento que ninguém está pedindo hoje. Ver `docs/fase3-relatorio.md` para a justificativa completa dessa fronteira.
- O auto-reply (`whatsapp.process_inbound`) e o hand-off legado ao n8n (`workflow.trigger`) rodam **em paralelo** por padrão — quem já usa n8n para gerar a resposta deve desativar `AUTO_REPLY_ENABLED` para o contato não receber duas respostas à mesma mensagem.
- **Nota de transparência sobre cobertura de testes**: `webhooks/router.py` e os handlers de envio em `api/whatsapp.py` mostram uma cobertura de linha aparentemente baixa na ferramenta `coverage.py` (investigado a fundo: não é cache de bytecode, não é ordem de import, não é specífico do plugin `pytest-cov` — reproduz com `coverage run` puro). A correção comportamental dessas rotas está provada por asserções diretas em ~20 testes de integração (status HTTP correto por cenário, linhas exatas persistidas no banco, payloads exatos de job) — evidência mais forte que a métrica de linha para este caso específico. Ver `docs/fase4.1-relatorio.md` para os detalhes da investigação.
- **Custo/latência do Cognitive Pipeline**: intenção, prioridade e planejamento são, cada um, uma chamada LLM independente (decisão real, não regra fixa) — até 3 chamadas antes mesmo da execução do agente escolhido. Deliberado (decisões independentes e testáveis > uma única chamada monolítica), mas é um custo real por mensagem; se o volume justificar, a Fase 4.3 pode combinar intenção+prioridade+planejamento numa única chamada de function calling sem mudar a interface pública de nenhum dos três componentes.
- **E-mail como domínio isolado de gateway único** (Sprint 1): em vez de dar as tools de Gmail a todo agente que pudesse se beneficiar delas, só `assistant` as recebeu — qualquer outro agente que precise de contexto de e-mail passa pelo Cognitive Planner, que já sabia rotear uma etapa para outro agente. Menos superfície de ataque (só um agente pode tocar o domínio), ao custo de uma etapa extra de planejamento quando um agente especializado precisa de e-mail; aceitável porque isso ainda não acontece em nenhum fluxo real desta sprint.
- **`AIOrchestrator.run` ganhou `memories`/`history` opcionais** em vez de um novo método paralelo — menos superfície de API, mas significa que qualquer chamador futuro pode, sem querer, pular o auto-fetch de memória passando `memories=[]`. Aceitável hoje (só o Cognitive Pipeline os usa); documentado para quem vier adicionar um terceiro chamador.
- **Composição de resposta multi-etapa é concatenação simples** (`CognitivePipeline._compose_reply`), não uma síntese via LLM — mais barato e mais previsível, mas uma resposta de duas etapas pode soar como duas respostas coladas em vez de um texto único e fluido. Ver riscos remanescentes em `docs/fase4.2-relatorio.md`.
