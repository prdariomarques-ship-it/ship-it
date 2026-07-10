"""Tools over contacts, memory and WhatsApp sending."""
import json

from agents.tools.base import Tool, ToolContext, ok
from memory.manager import memory_manager
from repositories.contact import ContactRepository


def _not_authorized(message: str) -> str:
    """Denial envelope for the cross-contact isolation checks below — a
    technical decision made in code, never left to the LLM's judgment."""
    return json.dumps({"error": message})


async def _find_contact(context: ToolContext, query: str) -> str:
    repository = ContactRepository(context.db)
    contact = await repository.get_by_phone(query)
    if contact is None:
        matches = await repository.search_by_name(query, limit=1)
        contact = matches[0] if matches else None

    # PROD-005: a conversation scoped to one contact can only ever look up
    # that same contact — never another contact's PII, regardless of what
    # the model asks for.
    if context.contact_id is not None and (contact is None or contact.id != context.contact_id):
        return _not_authorized("not authorized to look up a contact other than the current conversation")

    if contact is None:
        return ok(found=False)
    return ok(
        found=True,
        contact={
            "id": contact.id,
            "name": contact.name,
            "phone": contact.phone,
            "categories": contact.categories,
            "tags": contact.tags,
            "summary": contact.summary,
            "preferences": contact.preferences,
            "last_interaction_at": contact.last_interaction_at,
        },
    )


async def _search_memory(context: ToolContext, query: str, contact_id: int | None = None) -> str:
    results = await memory_manager.long_term_search(query=query, limit=5, contact_id=contact_id)
    return ok(memories=results)


async def _store_memory(context: ToolContext, content: str, contact_id: int | None = None) -> str:
    memory_id = await memory_manager.remember(
        context.db, content=content, source="agent", contact_id=contact_id
    )
    return ok(memory_id=memory_id)


async def _update_contact_preference(
    context: ToolContext, contact_id: int, key: str, value: str
) -> str:
    try:
        preferences = await memory_manager.set_preference(context.db, contact_id, key, value)
    except ValueError:
        return ok(found=False)
    return ok(found=True, preferences=preferences)


async def _send_whatsapp(context: ToolContext, to: str, message: str) -> str:
    # PROD-005: technical isolation, enforced here (not by prompt instructions).
    # A conversation scoped to a contact can only message that same contact;
    # otherwise (no conversation scope — e.g. an admin using the dashboard
    # directly) the recipient must already be a known contact, so the model
    # can never invent an arbitrary destination number out of thin air.
    from providers.whatsapp.base import normalize_phone

    target = normalize_phone(to)
    repository = ContactRepository(context.db)
    if context.contact_id is not None:
        contact = await repository.get(context.contact_id)
        if contact is None or not contact.phone or normalize_phone(contact.phone) != target:
            return _not_authorized("not authorized to message a recipient other than the current conversation")
    else:
        contact = await repository.get_by_phone(target)
        if contact is None:
            return _not_authorized("recipient is not a known contact")

    # Deliver through the job queue so sends survive provider hiccups (retry).
    from jobs.service import JobService

    job = await JobService(context.db).enqueue(
        "whatsapp.send_text", {"to": to, "content": message}
    )
    return ok(queued=True, job_id=job.id)


find_contact_tool = Tool(
    name="find_contact",
    description="Busca um contato pelo nome ou telefone e retorna seu perfil, resumo e preferências.",
    handler=_find_contact,
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Nome ou telefone"}},
        "required": ["query"],
    },
)

search_memory_tool = Tool(
    name="search_memory",
    description="Busca semântica na memória permanente do Dario OS.",
    handler=_search_memory,
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "contact_id": {"type": "integer", "description": "Restringir a um contato"},
        },
        "required": ["query"],
    },
)

store_memory_tool = Tool(
    name="store_memory",
    description="Grava uma informação importante na memória permanente.",
    handler=_store_memory,
    parameters={
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "contact_id": {"type": "integer"},
        },
        "required": ["content"],
    },
)

update_contact_preference_tool = Tool(
    name="update_contact_preference",
    description=(
        "Salva ou atualiza uma preferência estruturada de um contato "
        "(ex: horário de entrega preferido, forma de contato preferida)."
    ),
    handler=_update_contact_preference,
    parameters={
        "type": "object",
        "properties": {
            "contact_id": {"type": "integer"},
            "key": {"type": "string", "description": "Nome da preferência, ex: 'horario_entrega'"},
            "value": {"type": "string"},
        },
        "required": ["contact_id", "key", "value"],
    },
)

send_whatsapp_tool = Tool(
    name="send_whatsapp_message",
    description="Envia uma mensagem de WhatsApp para um número (fila com retry).",
    handler=_send_whatsapp,
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Telefone internacional, ex: 5511999999999"},
            "message": {"type": "string"},
        },
        "required": ["to", "message"],
    },
)
