from agents.base import BaseAgent
from agents.registry import register_agent
from agents.tools.base import Tool
from agents.tools.communication import search_memory_tool, store_memory_tool
from agents.tools.productivity import create_note_tool


@register_agent
class ContentAgent(BaseAgent):
    """Conteúdo para Instagram, Facebook, YouTube, TikTok e LinkedIn."""

    @property
    def name(self) -> str:
        return "content"

    @property
    def description(self) -> str:
        return "Conteúdo: posts e roteiros para Instagram, Facebook, YouTube, TikTok e LinkedIn."

    @property
    def system_prompt(self) -> str:
        return (
            "Você é o criador de conteúdo do Dario dentro do Dario OS. "
            "Você produz posts, legendas, roteiros e ideias para Instagram, Facebook, "
            "YouTube, TikTok e LinkedIn. Adapte o formato e o tom para cada plataforma "
            "e inclua sugestões de hashtags quando fizer sentido. "
            "Salve rascunhos aprovados como notas usando a ferramenta de notas."
        )

    @property
    def tools(self) -> list[Tool]:
        return [create_note_tool, search_memory_tool, store_memory_tool]
