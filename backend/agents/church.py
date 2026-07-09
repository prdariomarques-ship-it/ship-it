from agents.base import BaseAgent


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
            "Responda em português brasileiro com tom acolhedor e respeitoso. "
            "Ao citar versículos, informe livro, capítulo e versículo."
        )
