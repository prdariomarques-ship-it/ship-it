from agents.base import BaseAgent
from agents.registry import register_agent
from agents.tools.base import Tool
from agents.tools.communication import search_memory_tool, store_memory_tool
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
            "tarefas, eventos e notas reais do sistema."
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
        ]
