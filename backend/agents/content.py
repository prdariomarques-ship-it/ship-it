from agents.base import BaseAgent


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
            "YouTube, TikTok e LinkedIn. Responda em português brasileiro. "
            "Adapte o formato e o tom para cada plataforma e inclua sugestões de "
            "hashtags quando fizer sentido."
        )
