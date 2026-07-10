from agents.base import BaseAgent
from agents.registry import register_agent
from agents.tools.base import Tool
from agents.tools.communication import (
    find_contact_tool,
    search_memory_tool,
    send_whatsapp_tool,
    store_memory_tool,
    update_contact_preference_tool,
)
from agents.tools.domain import (
    add_prayer_request_tool,
    add_store_customer_tool,
    list_church_members_tool,
    list_store_customers_tool,
)
from agents.tools.gcalendar import (
    check_google_calendar_availability_tool,
    create_google_calendar_event_tool,
    delete_google_calendar_event_tool,
    list_google_calendars_tool,
    search_google_calendar_events_tool,
    update_google_calendar_event_tool,
)
from agents.tools.gcontacts import (
    create_google_contact_tool,
    delete_google_contact_tool,
    search_google_contacts_tool,
    update_google_contact_tool,
)
from agents.tools.gdrive import (
    index_google_drive_file_tool,
    index_google_drive_folder_tool,
    list_google_drive_files_tool,
    read_google_drive_file_tool,
    search_google_drive_files_tool,
    summarize_google_drive_document_tool,
    update_google_drive_index_tool,
)
from agents.tools.mail import (
    detect_pending_email_actions_tool,
    read_email_thread_tool,
    search_emails_tool,
    summarize_email_thread_tool,
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
            "(agenda, tarefas, notas, igreja, loja, contatos, documentos). "
            "Para perguntas sobre documentos já indexados (ex: 'qual documento fala "
            "sobre X'), use primeiro a ferramenta search_memory antes de tentar buscar "
            "no Google Drive do zero. "
            "Responda mensagens de forma educada, calorosa e objetiva. "
            "Use as memórias e o perfil do contato para personalizar a resposta. "
            "Nunca invente compromissos ou informações: consulte as ferramentas. "
            "Se não souber, diga que o Dario responderá em breve. "
            "Sua resposta de texto final é enviada automaticamente ao contato que "
            "está te escrevendo agora — não use a ferramenta de envio de WhatsApp "
            "para isso. Use-a apenas para avisar OUTRA pessoa (diferente de quem "
            "está te escrevendo), quando o pedido exigir isso explicitamente."
        )

    @property
    def tools(self) -> list[Tool]:
        return [
            find_contact_tool,
            search_memory_tool,
            store_memory_tool,
            update_contact_preference_tool,
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
            search_emails_tool,
            read_email_thread_tool,
            summarize_email_thread_tool,
            detect_pending_email_actions_tool,
            list_google_calendars_tool,
            search_google_calendar_events_tool,
            create_google_calendar_event_tool,
            update_google_calendar_event_tool,
            delete_google_calendar_event_tool,
            check_google_calendar_availability_tool,
            search_google_contacts_tool,
            create_google_contact_tool,
            update_google_contact_tool,
            delete_google_contact_tool,
            list_google_drive_files_tool,
            search_google_drive_files_tool,
            read_google_drive_file_tool,
            index_google_drive_file_tool,
            index_google_drive_folder_tool,
            summarize_google_drive_document_tool,
            update_google_drive_index_tool,
        ]
