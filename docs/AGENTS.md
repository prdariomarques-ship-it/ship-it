# Agentes

Um agente do Dario OS é uma classe que estende `agents.base.BaseAgent` e declara identidade + system prompt + ferramentas. Tudo o mais — memória, planejamento de mensagens, loop de function calling, seleção pelo Cognitive Pipeline — é infraestrutura compartilhada; o agente não reimplementa nada disso.

## Agentes existentes

| Agente | Arquivo | Domínio | Ferramentas |
| --- | --- | --- | --- |
| `personal` | `agents/personal_agent.py` | Agenda, lembretes, notas, pesquisa, resumos | tarefas, eventos, notas, memória |
| `church` | `agents/church_agent.py` | Oração, escalas, cultos, avisos, membros | membros, pedidos de oração, eventos, memória |
| `store` | `agents/store_agent.py` | Produtos, pedidos, clientes, orçamentos | clientes, contatos, memória, preferências |
| `content` | `agents/content_agent.py` | Conteúdo para redes sociais, pesquisa, documentos | notas, memória |
| `assistant` | `agents/assistant_agent.py` | Generalista — atende o WhatsApp, acesso a todos os domínios | todas + envio de WhatsApp + preferências |

`assistant` é o agente padrão usado como fallback: quando o Cognitive Planner nomeia um agente inexistente, ou quando a classificação de intenção degrada para a heurística sem um mapeamento intenção→agente, a etapa cai para `assistant`.

## Anatomia de um agente

```python
# agents/weather_agent.py
from agents.base import BaseAgent
from agents.registry import register_agent
from agents.tools.base import Tool

@register_agent
class WeatherAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "Previsão do tempo"

    @property
    def system_prompt(self) -> str:
        return "Você informa previsão do tempo usando as ferramentas disponíveis..."

    @property
    def tools(self) -> list[Tool]:
        return [get_forecast_tool]
```

Quatro propriedades obrigatórias (`name`, `description`, `system_prompt`) mais uma opcional (`tools`, vazia por padrão). Tudo o resto vem de `BaseAgent.run`, herdado sem overrides na prática:

```python
async def run(self, db, user, message, contact_id=None, memories=None, history=None) -> AgentResult:
    if memories is None:
        memories = await memory_manager.build_agent_context(message, contact_id)["memories"]  # best-effort
    messages = self.planner.build_messages(self.system_prompt, message, memories, history=history)
    executor = AgentExecutor(get_llm_provider(), self.tools)
    result = await executor.run(messages, ToolContext(db=db, user=user))
    result.memories_used = len(memories)
    return result
```

- **`memories`/`history` opcionais** (Fase 4.2): quando `None` (todo chamador antes da Fase 4.2, e ainda hoje `/api/chat` e `/api/agents/{name}/run`), o agente busca sua própria memória de longo prazo. Quando fornecidos (só pelo Cognitive Pipeline), o agente pula o auto-fetch e usa o que já veio pronto — evita buscar memória duas vezes para o mesmo plano.
- **`planner`** (`agents/planner.py::Planner`) monta a lista de mensagens: system prompt + memórias formatadas + histórico de conversa + a mensagem do usuário. É deliberadamente burro — nenhuma decisão, só montagem de prompt. Não confundir com `orchestrator.planning.CognitivePlanner` (decide o quê fazer); este aqui só decide como apresentar o pedido ao modelo.
- **`executor`** (`agents/executor.py::AgentExecutor`) roda o loop plan→act→observe: pede a próxima ação ao modelo, executa as tool calls pedidas através do Tool Registry, alimenta os resultados de volta, repete até uma resposta final ou o orçamento de iterações (`AGENT_MAX_ITERATIONS`) acabar.

## Instalando um agente novo (convenção de pasta)

Nenhum arquivo central lista agentes. `agents/registry.py` descobre todo módulo `agents/*_agent.py` automaticamente (`pkgutil.iter_modules`, uma vez, na primeira chamada a `get_agent`/`list_agents`); o decorator `@register_agent` roda no import e o agente já aparece em `GET /api/agents`, fica disponível em `/api/chat`, `/api/agents/{name}/run`, e — automaticamente, sem nenhuma mudança de código — se torna uma opção válida para o Cognitive Planner escolher, porque a lista de agentes que o Planner oferece ao modelo vem de `agents.registry.list_agents()` em tempo de execução.

## Como um agente é escolhido

Dois caminhos, ambos convergindo no mesmo `AIOrchestrator.run`:

1. **Escolha explícita** — `/api/chat` (dashboard) e `/api/agents/{name}/run` passam `agent_name` diretamente; nenhuma classificação acontece.
2. **Escolha cognitiva** (Fase 4.2, hoje só usada pelo auto-reply do WhatsApp) — o Cognitive Planner decide, por chamada de função ao LLM, qual agente cada etapa do plano usa; ver `docs/architecture.md#cognitive-pipeline-fase-42` para o fluxo completo e `docs/architecture.md#fluxo-de-agentes` para o diagrama de sequência interno de `BaseAgent.run`.

## Observabilidade por agente

Toda execução — de qualquer um dos dois caminhos — passa por `AIOrchestrator.run`, que publica `agent.selected`/`agent.replied`/`agent.failed` no Event Bus e grava `darioos_agent_runs_total{agent,provider,status}`, `darioos_agent_run_duration_seconds{agent}`, tokens e custo estimado. Nenhum agente precisa se instrumentar.
