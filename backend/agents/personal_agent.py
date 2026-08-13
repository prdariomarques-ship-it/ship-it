from agents.base import BaseAgent
from agents.registry import register_agent
from agents.tools.base import Tool
from agents.tools.communication import search_memory_tool, store_memory_tool
from agents.tools.flowcore_tools import (
    flowcore_health_tool,
    macro_scores_tool,
    observer_events_tool,
    observer_health_tool,
    portfolio_impact_tool,
    portfolio_list_tool,
    portfolio_summary_tool,
    regime_signals_tool,
)
from agents.tools.productivity import (
    complete_task_tool,
    create_event_tool,
    create_note_tool,
    create_task_tool,
    list_events_tool,
    list_tasks_tool,
)


@register_agent
class PersonalAgent(BaseAgent):
    """Agenda, lembretes, notas, pesquisa e resumos."""

    @property
    def name(self) -> str:
        return "personal"

    @property
    def description(self) -> str:
        return "Assistente pessoal: agenda, lembretes, notas, pesquisa e resumos."

    @property
    def system_prompt(self) -> str:
        return (
            "Você é o assistente pessoal do Dario dentro do Dario OS. "
            "Você ajuda com agenda, lembretes, notas, pesquisas e resumos. "
            "Seja direto e prático. Use as ferramentas para criar e consultar "
            "tarefas, eventos e notas reais do sistema. "
            "Para perguntas de mercado/investimentos (\"como está o mercado?\", "
            "\"meu portfólio está bem exposto?\"), use as ferramentas do FlowCore "
            "(flowcore_*) — elas trazem números e recomendações determinísticas "
            "do motor de inteligência de mercado. Responda com base nos dados "
            "reais retornados, sem inventar cotações nem previsões. "
            "Se o FlowCore estiver indisponível (health check com erro), diga "
            "que o motor de mercado está fora do ar e sugira verificar depois."
        )

    @property
    def tools(self) -> list[Tool]:
        return [
            create_task_tool,
            list_tasks_tool,
            complete_task_tool,
            create_event_tool,
            list_events_tool,
            create_note_tool,
            search_memory_tool,
            store_memory_tool,
            # FlowCore market-intelligence engine (REST shim — no shared
            # runtime/DB dependency with the Dario OS backend).
            flowcore_health_tool,
            macro_scores_tool,
            regime_signals_tool,
            observer_events_tool,
            observer_health_tool,
            portfolio_list_tool,
            portfolio_summary_tool,
            portfolio_impact_tool,
        ]
