# CurrentContext

`observation/models.py::CurrentContext` é a fotografia que o [Context Observation Engine](OBSERVATION_ENGINE.md) mantém: um snapshot plano, serializável em JSON, das sete dimensões do estado atual do dono do sistema. Não é uma nova fonte de verdade — cada campo é derivado de tabelas que já existem (`goals`, `tasks`, `calendar`, `logs`, `messages`, `jobs`, `embeddings`); perder a fotografia (restart, cache limpo) não perde nenhum dado durável, só a conveniência de já estar pronta (ver `docs/OBSERVATION_ENGINE.md#o-que-restart-safe-significa-aqui`).

## Forma

```python
class ContextItem(BaseModel):
    source: str    # ex: "goal", "task", "calendar", "event", "conversation", "job", "memory"
    content: str    # descrição legível, pronta para prompt/log — não um dict estruturado

class CurrentContext(BaseModel):
    user_id: int
    generated_at: datetime          # UTC, quando esta fotografia foi construída
    trigger: str                    # "scheduler" | "startup" | "event:<nome>"

    goals: list[ContextItem]
    tasks: list[ContextItem]
    calendar: list[ContextItem]
    recent_events: list[ContextItem]
    conversations: list[ContextItem]
    pending_work: list[ContextItem]
    memory: list[ContextItem]

    degraded_sources: list[str]     # nomes das dimensões cuja fonte falhou nesta build
```

`ContextItem` usa deliberadamente o mesmo par `{source, content}` que `orchestrator.context.Context.memories` já usa — quem já sabe ler um daquele formato sabe ler este, mesmo os dois sendo fotografias com ciclos de vida diferentes (ver a tabela comparativa em `docs/OBSERVATION_ENGINE.md`).

## As sete dimensões

| Campo | Fonte real | Filtro | Reaproveita |
| --- | --- | --- | --- |
| `goals` | `Goal` | `PENDING`, sem dependência pendente, ordenado por `priority_score` | `GoalService.ready_goals` — GoalManager |
| `tasks` | `Task` | `status=PENDING` | `SQLAlchemyRepository[Task]` |
| `calendar` | `CalendarEvent` | `starts_at >= agora`, mais próximo primeiro | consulta inline, mesmo padrão de `orchestrator/context.py` |
| `recent_events` | `LogEntry` (tabela `logs`) | mais recentes primeiro (`id.desc()`) | consulta inline, mesmo padrão de `api/routes.py`/`admin/service.py` |
| `conversations` | `Message` | mais recentes primeiro, qualquer contato | `MessageRepository.list()` |
| `pending_work` | `Job` | `QUEUED` + `RUNNING` | `JobRepository.list()` |
| `memory` | `Embedding` (metadados; não consulta o Qdrant) | mais recentes primeiro | `SQLAlchemyRepository[Embedding]` |

Cada dimensão é limitada a `OBSERVATION_CONTEXT_LIMIT` itens (padrão 5 — mesmo valor que `orchestrator.context._OWNER_CONTEXT_LIMIT` usa para metas/tarefas/agenda no Context Builder por mensagem).

## Best-effort: `degraded_sources`

Cada uma das sete fontes é buscada dentro de um `try/except` isolado (`ObservationContextBuilder.build`) — uma fonte que falhar (Qdrant fora do ar não afeta `memory` porque ele só lê Postgres, mas uma migração pendente ou uma tabela indisponível afetaria) fica com a lista vazia e seu nome entra em `degraded_sources`; as outras seis continuam normalmente. Nunca uma exceção de uma fonte derruba a fotografia inteira — mesma filosofia de `orchestrator.context.ContextBuilder` (goals/tasks/calendar "nunca são requisito, sempre um enriquecimento").

```python
context = await ObservationContextBuilder().build(db, user)
if "memory" in context.degraded_sources:
    logger.warning("Fotografia sem memória nesta rodada")
```

## Como ler a fotografia atual

`ContextObservationEngine.current(user_id)` é uma leitura síncrona, sem I/O — dicionário em memória, não uma query:

```python
from observation.engine import context_observation_engine

snapshot = context_observation_engine.current(owner.id)
if snapshot is None:
    ...  # nenhuma fotografia ainda (processo acabou de subir) — ver limitação em OBSERVATION_ENGINE.md
elif snapshot.age_seconds() > 900:
    ...  # fotografia com mais de 15 min — caller decide se isso é aceitável
```

`is_empty` e `item_count` (propriedades computadas) ajudam a distinguir "nenhuma fotografia" (`current() is None`) de "fotografia construída, mas o dono não tem nada pendente em nenhuma das sete dimensões" (`current().is_empty is True`) — os dois casos parecem "vazio" superficialmente, mas significam coisas diferentes para quem consome.

## Exemplo (serializado)

```json
{
  "user_id": 1,
  "generated_at": "2026-07-17T14:32:05.120000+00:00",
  "trigger": "event:goal.created",
  "goals": [
    {"source": "goal", "content": "Aprender violão; prioridade high"}
  ],
  "tasks": [],
  "calendar": [
    {"source": "calendar", "content": "Reunião com cliente em 2026-07-18T10:00:00+00:00"}
  ],
  "recent_events": [
    {"source": "event", "content": "[info] goal:1: Goal 1 created"}
  ],
  "conversations": [
    {"source": "conversation", "content": "contato 3, recebida: oi, tudo bem?"}
  ],
  "pending_work": [
    {"source": "job", "content": "contact.summarize (queued, tentativa 0/3)"}
  ],
  "memory": [],
  "degraded_sources": []
}
```
