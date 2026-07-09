from agents.base import BaseAgent
from agents.tools.base import Tool
from agents.tools.communication import (
    find_contact_tool,
    search_memory_tool,
    send_whatsapp_tool,
    store_memory_tool,
)
from agents.tools.domain import (
    add_prayer_request_tool,
    add_store_customer_tool,
    list_church_members_tool,
    list_store_customers_tool,
)
from agents.tools.productivity import (
    complete_task_tool,
    create_event_tool,
    create_note_tool,
    create_task_tool,
    list_events_tool,
    list_tasks_tool,
)


class AssistantAgent(BaseAgent):
    """Agente geral: atende o WhatsApp e orquestra todos os domínios."""

    @property
    def name(self) -> str:
        return "assistant"

    @property
    def description(self) -> str:
        return "Assistente geral: atende o WhatsApp e tem acesso a todos os domínios do Dario OS."

    @property
    def system_prompt(self) -> str:
        return (
            "Você é o assistente geral do Dario dentro do Dario OS, responsável por "
            "atender conversas do WhatsApp e executar pedidos em qualquer módulo "
            "(agenda, tarefas, notas, igreja, loja, contatos). "
            "Responda mensagens de forma educada, calorosa e objetiva. "
            "Use as memórias e o perfil do contato para personalizar a resposta. "
            "Nunca invente compromissos ou informações: consulte as ferramentas. "
            "Se não souber, diga que o Dario responderá em breve."
        )

    @property
    def tools(self) -> list[Tool]:
        return [
            find_contact_tool,
            search_memory_tool,
            store_memory_tool,
            send_whatsapp_tool,
            create_task_tool,
            list_tasks_tool,
            complete_task_tool,
            create_event_tool,
            list_events_tool,
            create_note_tool,
            list_church_members_tool,
            add_prayer_request_tool,
            list_store_customers_tool,
            add_store_customer_tool,
        ]
