from agents.base import BaseAgent


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
            "Seja direto, prático e responda sempre em português brasileiro. "
            "Quando o pedido envolver criar tarefas ou eventos, descreva exatamente "
            "o que deve ser criado (título, data, hora) para confirmação."
        )
