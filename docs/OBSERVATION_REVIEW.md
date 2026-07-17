# Observation Engine — Architecture Review

Revisão pós-implementação do [Context Observation Engine](OBSERVATION_ENGINE.md) contra os dez princípios pedidos, mais uma verificação item a item das oito peças. Feita depois do código estar pronto e testado (`fb6ed5e`), antes do commit final ser aceito como correto — não é um exercício de retórica: encontrou dois problemas reais, ambos corrigidos antes deste commit (`7915605` na branch remota, após rebase sobre dois commits não relacionados que chegaram no meio da revisão).

## Resultado: dois problemas reais encontrados e corrigidos

A revisão não foi só confirmação — comparar `observation/builder.py` com `orchestrator/context.py` linha a linha achou duplicação de verdade:

| Problema | Onde | Correção |
| --- | --- | --- |
| `_TaskRepo(SQLAlchemyRepository[Task])` declarado identicamente em dois arquivos | `orchestrator/context.py` e `observation/builder.py` | Extraído para `repositories/task.py::TaskRepository` — preenche uma lacuna real (era o único modelo de domínio sem repositório dedicado, ao lado de `Embedding`) em vez de inventar uma camada nova |
| `_describe_goal`/`_describe_task`/`_describe_event` copiados quase byte a byte (uma até perdeu a anotação de tipo `goal: Goal` na cópia) | mesmos dois arquivos | Extraído para `services/descriptions.py::describe_goal/describe_task/describe_calendar_event` — mesmo idioma que `services/messaging.py` já usa ("dois call sites não podem divergir") |

Por que isso importava de verdade, não só estilo: as duas cópias já tinham divergido (uma perdeu a anotação de tipo) na primeira geração de código — prova de que duplicação nesse formato tende a divergir silenciosamente assim que alguém mexe em um lado e esquece o outro. Se um `Goal` com `deadline` precisasse mudar de formato amanhã, só uma das duas fontes de contexto mudaria, e o dono veria descrições inconsistentes de uma mesma meta dependendo de qual motor gerou o texto.

`services/descriptions.py` e `repositories/task.py` foram escolhidos como o lar, não `orchestrator/` nem `observation/`, deliberadamente: se `observation/builder.py` importasse de `orchestrator/context.py` diretamente, criaria uma dependência `observation -> orchestrator` que se tornaria circular no dia em que `CognitivePipeline` passasse a consumir `ContextObservationEngine.current()` (extension point documentado, ver "Future extension points" abaixo) — `orchestrator -> observation` e `observation -> orchestrator` ao mesmo tempo. `services/` e `repositories/` já são camadas-folha que nenhum dos dois domínios depende do outro para alcançar; ambos podem depender delas sem risco.

Depois da correção: suíte completa (867 testes) verde, `ruff check` e `mypy --ignore-missing-imports` limpos em todos os arquivos tocados.

## Verificação item a item

### 1. Observation Engine (`observation/engine.py`)
Cache em memória por `user_id` (`dict[int, CurrentContext]`), sem I/O em `current()`. Um `asyncio.Lock` por usuário evita duas reconstruções concorrentes (um tick do scheduler e um pull-forward de evento chegando ao mesmo tempo) — mas isso protege *dentro de um processo*; não sincroniza entre réplicas (ver Known Limitations). `reset()` existe só para testes, nunca chamado em código de produção. Nenhuma escrita em banco acontece aqui — só cache local e publicação de evento.

### 2. Context Builder (`observation/builder.py`, agora `ObservationContextBuilder`)
Sete fontes, cada uma num `try/except` isolado (`ObservationContextBuilder.build`), nunca derruba a fotografia inteira por uma fonte fora do ar. 100% leitura — nenhuma das sete `_gather_*` chama `.create`/`.update`/`.delete` em nenhum repositório. Confirmado por leitura direta do código nesta revisão (não só pela suíte de testes), com um `grep` específico procurando qualquer chamada de escrita — nenhuma encontrada.

### 3. CurrentContext (`observation/models.py`)
Pydantic puro, sem tabela própria — cada campo é derivado de uma tabela que já existe (`goals`, `tasks`, `calendar`, `logs`, `messages`, `jobs`, `embeddings`). Não duplica estado: é um *read model* descartável, não uma segunda fonte de verdade concorrente com nenhuma delas. Mesma filosofia que `docs/architecture.md#por-que-não-existe-um-statemanager-central` já formaliza para o resto do runtime.

### 4. Observation Scheduler (`observation/scheduler.py`)
Não é um componente novo — é um `job_handler` (`observation.tick`) rodando no `JobWorker` já existente. Auto-reagendável: cada execução enfileira a própria próxima execução antes de retornar. `start()` é idempotente via `JobRepository.pending_by_name` (novo método, único ponto tocado em código pré-existente além do `metrics.py`/`config.py` aditivos) — um restart nunca cria uma segunda cadeia concorrente. Verificado com um teste que efetivamente simula um restart (`test_a_fresh_engine_instance_is_repopulated_from_the_same_job_chain`), não só por inspeção.

### 5. Event subscriptions (`observation/events.py`)
Assina `goal.*`/`job.*`/`agent.*` via `EventBus.subscribe` (curinga de domínio, mecanismo já existente, nenhuma extensão ao `EventBus` em si). Guard-rail testado contra autodisparo: eventos `job.*` do próprio `observation.tick` são ignorados (checagem por `job_name`), ou cada tick puxaria o próximo tick pra agora indefinidamente. `register_event_subscribers()` é chamado explicitamente do `main.py`, nunca como side effect de importação — mesmo padrão de `jobs.handlers.register_event_subscribers`.

### 6. JobWorker integration
Nenhum código em `observation/` toca `JobWorker` diretamente — nem importa a classe, nem chama métodos internos. Toda a integração passa pelas duas superfícies públicas que já existem: o decorator `@job_handler` (registro) e `JobService.enqueue` (agendamento). Verificado por grep nesta revisão: as únicas menções a `JobWorker` em `observation/` são comentários explicando *por que* não existe um scheduler novo.

### 7. GoalManager integration
Só leitura: `GoalService(db).ready_goals(...)` — mesma chamada que `orchestrator.context.ContextBuilder` já fazia. Nenhuma chamada a `create_goal`/`update_status`/`approve_goal`/`add_dependency` em nenhum arquivo de `observation/`, confirmado por grep. A integração de escrita/evento vem só do lado de fora: `GoalService` já publica `goal.*` no Event Bus (`goals/events.py`, código não tocado), e é isso que `observation/events.py` assina.

### 8. Cognitive Pipeline integration
Nenhum import de `orchestrator.pipeline` ou `orchestrator.service` em `observation/` (confirmado por grep — as únicas ocorrências da palavra "orchestrator" em `observation/*.py` são referências em docstring). A reutilização pedida na missão acontece por evento, não por chamada direta: `orchestrator/service.py::AIOrchestrator.run` já publica `agent.selected`/`agent.replied`/`agent.failed`, e `observation/events.py` assina `agent.*` — o Cognitive Pipeline nunca precisa saber que o Observation Engine existe. Ver "Future extension points" para o caminho inverso (pipeline lendo `CurrentContext`), que existe como capacidade mas não foi ligado nesta milestone.

## Checklist dos dez princípios

| Princípio | Veredito | Evidência |
| --- | --- | --- |
| Sem estado duplicado | ✅ | `CurrentContext` é derivado e descartável, não uma segunda fonte de verdade (item 3 acima) |
| Sem repositórios duplicados | ✅ (corrigido) | `TaskRepository` extraído para `repositories/task.py`; `_EmbeddingRepo` não tinha duplicata em nenhum outro lugar do código, mantido local |
| Sem serviços duplicados | ✅ (corrigido) | `ObservationContextBuilder` e `ContextBuilder` são serviços legitimamente distintos (escopo/gatilho/consumidor diferentes — ver tabela em `docs/OBSERVATION_ENGINE.md`); a duplicação real era nas funções auxiliares, não nos serviços em si, e foi extraída para `services/descriptions.py` |
| Sem dependências circulares | ✅ | `grep` confirmando que nada em `orchestrator/`, `goals/`, `jobs/`, `events/`, `repositories/`, `models/`, `memory/` importa de `observation/` |
| Sem polling onde eventos bastam | ⚠️ trade-off documentado, não violação | Ver "Trade-offs" abaixo |
| Sem escritas ocultas no banco | ✅ | Builder é 100% leitura; scheduler/eventos só escrevem a linha `Job` esperada (`enqueue`/`update(scheduled_at=...)`) |
| Restart-safe | ✅ | Provado por teste real (`test_a_fresh_engine_instance_is_repopulated_from_the_same_job_chain`), não só por design |
| Idempotência | ✅ | `start()` via `pending_by_name`; claim de job via `SELECT ... FOR UPDATE SKIP LOCKED` (herdado do `JobWorker`); pull-forward de evento é idempotente (repetir só resseta `scheduled_at`, nunca cria linha nova) |
| Orientado a eventos | ✅ | Assina `goal.*`/`job.*`/`agent.*`, publica `observation.context_updated`, guard-rail contra autodisparo testado |
| Reaproveita infraestrutura existente | ✅ (corrigido) | `EventBus`, `JobWorker`/fila de jobs, `GoalService`, `JobRepository`, `MessageRepository`, e agora `TaskRepository`/`services/descriptions.py` em vez de reimplementações locais |

## Trade-offs

- **Tick periódico (5 min) além dos eventos.** Eventos cobrem "algo mudou agora" (meta criada, job concluído, agente respondeu); não cobrem obsolescência por passagem do tempo — um evento de calendário que vira passado, ou uma janela longa sem nenhuma atividade em `goal.*`/`job.*`/`agent.*`. O tick periódico é o piso de frescor para esses casos. Não é "polling onde evento bastaria": é o `JobWorker` (que já faz seu próprio polling de 2s independente desta feature) processando uma linha de job como qualquer outra — nenhum novo loop de polling foi criado.
- **Cache em memória, não persistido.** Perder a fotografia num restart é aceitável porque nada nela é dado durável — está tudo em Postgres antes de estar em `CurrentContext`. O custo é uma janela de `None` entre o restart e o primeiro tick processado (documentado em `docs/OBSERVATION_ENGINE.md`).
- **`pending_work` corta `QUEUED`+`RUNNING` sem ponderar por idade/prioridade.** Suficiente para "o que está em andamento agora"; não é uma fila priorizada.
- **`recent_events` inclui o próprio ruído de bookkeeping do `observation.tick`.** Cada execução do tick já gera `job.started`/`job.succeeded` na tabela `logs` (mecanismo existente, `jobs/events.py`, não algo novo) — com `OBSERVATION_CONTEXT_LIMIT=5` e um tick a cada 5 minutos, esses dois eventos tendem a ocupar boa parte do top-5 de `recent_events`, competindo com sinal real (criação de meta, job de negócio concluído). Não é uma escrita oculta (o mecanismo é público e documentado), mas reduz o valor prático dessa dimensão específica — registrado como limitação conhecida, não corrigido nesta revisão porque filtrar `source == "job:observation.tick"` é uma decisão de produto (quanto do próprio bookkeeping do motor deveria aparecer como "evento recente"?) melhor tomada com um consumidor real em mãos, não adivinhada agora.

## Future extension points

- **Cognitive Pipeline lendo `CurrentContext`.** `context_observation_engine.current(user.id)` é leitura síncrona, sem I/O — pronta para `CognitivePipeline.process` consultar como um passo adicional ("o sistema sempre sabe seu estado atual antes de decidir", literalmente). Não ligado nesta milestone porque não há consumidor real que precise disso ainda além do princípio geral da missão — mesma lógica já aplicada a outras capacidades adiadas em `docs/architecture.md#capacidades-deliberadamente-adiadas`.
- **`GET /api/observation` (ou endpoint equivalente) expondo `CurrentContext` do dono.** Hoje só é acessível via `context_observation_engine.current(user_id)` dentro do processo Python — nenhuma rota HTTP existe. Natural para uma futura tela de admin ("o que o sistema sabe agora").
- **Assinantes de `observation.context_updated`.** O evento já é publicado a cada `observe()`; nenhum handler assina ainda (mesmo estado que `agent.selected`/`agent.replied` tinham antes da existência de qualquer AI Console).
- **Fotografias por usuário além do dono.** `CurrentContext` já carrega `user_id`; observar mais de um usuário exigiria só chamar `observe()` para cada um — nenhuma mudança estrutural.

## Known limitations

- **Cache não é compartilhado entre réplicas.** Se o `JobWorker` rodar em mais de um processo/réplica (arquitetura já suportada pelo `SELECT ... FOR UPDATE SKIP LOCKED`, ver `docs/architecture.md`), só a réplica que efetivamente processar um dado `observation.tick` atualiza o próprio cache local — as outras réplicas podem nunca observar aquele tick e ficar com `current()` desatualizado ou `None` indefinidamente. Aceitável hoje porque o deployment padrão documentado é o worker no mesmo processo da API (`docs/architecture.md`, seção "Decisões e trade-offs": "Worker de jobs no mesmo processo da API por padrão") e o sistema é single-owner/single-instância por natureza (ver `CLAUDE.md` do usuário). Resolver isso de verdade exigiria um cache compartilhado entre processos (Redis, por exemplo) — infraestrutura nova, fora do escopo explicitamente definido para esta missão ("não introduza... provider, banco... novo").
- **Janela de `None` após um restart frio.** Documentado em `docs/OBSERVATION_ENGINE.md` — `current()` retorna `None` até o primeiro tick pós-restart terminar. Quem precisa de uma garantia "nunca `None`" deve tratar esse caso explicitamente.
- **`recent_events` com ruído do próprio motor** — ver Trade-offs acima.
- **Escopo single-owner.** Só o primeiro admin (`get_first_admin`) é observado — consistente com o resto do código (`orchestrator/context.py`, `jobs/handlers.py`), não uma limitação introduzida por esta peça.

## Por que esta implementação segue a arquitetura do projeto

Toda peça pedida (Engine, Builder, Scheduler, eventos) resolve em algo que já existe no runtime documentado em `docs/architecture.md#dario-os-core-runtime`, não em um componente paralelo:

- **Scheduler** = o `JobWorker` já existente + um handler novo, não um novo timer/loop. Mesmo raciocínio que `docs/architecture.md` já aplicou ao `GoalManager`/`Cognitive Pipeline` ("5 dos 6 componentes já existiam... só X era genuinamente novo").
- **Estado** = distribuído por domínio, cache descartável derivado de Postgres — não um `StateManager` central, respeitando a decisão já documentada e justificada em `docs/architecture.md#por-que-não-existe-um-statemanager-central`.
- **Reuso** = `EventBus`, `GoalManager` (`GoalService`), fila de jobs, repositórios — nenhum reimplementado; os dois pontos onde uma reimplementação começou a acontecer (`_TaskRepo`, `_describe_*`) foram pegos por esta revisão e corrigidos antes do commit final, exatamente o tipo de verificação que `docs/architecture.md` já demonstra (a cada nova missão, checar contra o código existente antes de assumir que algo é novo).
- **Honestidade sobre limites** = a seção "restart-safe" em `docs/OBSERVATION_ENGINE.md` e as limitações listadas aqui seguem o mesmo padrão que `docs/GOALS.md#o-que-resume-after-restart-significa-aqui-limite-deliberado` já estabeleceu: dizer exatamente o que é garantido e o que não é, em vez de uma implementação-fachada atrás de um nome que promete mais do que existe.
