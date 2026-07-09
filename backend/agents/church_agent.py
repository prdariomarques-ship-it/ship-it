from agents.base import BaseAgent
from agents.tools.base import Tool
from agents.tools.communication import search_memory_tool, store_memory_tool
from agents.tools.domain import add_prayer_request_tool, list_church_members_tool
from agents.tools.productivity import create_event_tool, list_events_tool


class ChurchAgent(BaseAgent):
    """Pedidos de oração, escalas, cultos, avisos e versículos."""

    @property
    def name(self) -> str:
        return "church"

    @property
    def description(self) -> str:
        return "Ministério: pedidos de oração, escalas, cultos, avisos e versículos."

    @property
    def system_prompt(self) -> str:
        return (
            "Você é o assistente de ministério do Dario dentro do Dario OS. "
            "Você ajuda com pedidos de oração, escalas de voluntários, programação de "
            "cultos, avisos para a igreja e sugestões de versículos bíblicos. "
            "Tom acolhedor e respeitoso. Ao citar versículos, informe livro, "
            "capítulo e versículo. Use as ferramentas para registrar pedidos de oração "
            "e consultar membros e eventos reais."
        )

    @property
    def tools(self) -> list[Tool]:
        return [
            list_church_members_tool,
            add_prayer_request_tool,
            create_event_tool,
            list_events_tool,
            search_memory_tool,
            store_memory_tool,
        ]
