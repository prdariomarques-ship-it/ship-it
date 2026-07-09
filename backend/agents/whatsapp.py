from agents.base import BaseAgent


class WhatsAppAgent(BaseAgent):
    """Conversa com contatos via WhatsApp (texto, imagem, PDF, áudio, localização)."""

    @property
    def name(self) -> str:
        return "whatsapp"

    @property
    def description(self) -> str:
        return "Atende conversas do WhatsApp: recebe e responde mensagens em nome do Dario."

    @property
    def system_prompt(self) -> str:
        return (
            "Você atende o WhatsApp do Dario dentro do Dario OS. "
            "Responda mensagens de contatos de forma educada, calorosa e objetiva, "
            "em português brasileiro. Use as memórias sobre o contato para personalizar "
            "a resposta. Nunca invente compromissos ou informações que não estejam nas "
            "memórias. Se não souber, diga que o Dario responderá em breve."
        )
