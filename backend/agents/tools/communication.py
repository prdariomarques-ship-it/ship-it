"""Tools over contacts, memory and WhatsApp sending."""
from agents.tools.base import Tool, ToolContext, ok
from memory.service import memory_service
from repositories.contact import ContactRepository


async def _find_contact(context: ToolContext, query: str) -> str:
    repository = ContactRepository(context.db)
    contact = await repository.get_by_phone(query)
    if contact is None:
        matches = await repository.search_by_name(query, limit=1)
        contact = matches[0] if matches else None
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
            "last_interaction_at": contact.last_interaction_at,
        },
    )


async def _search_memory(context: ToolContext, query: str, contact_id: int | None = None) -> str:
    results = await memory_service.search(query=query, limit=5, contact_id=contact_id)
    return ok(memories=results)


async def _store_memory(context: ToolContext, content: str, contact_id: int | None = None) -> str:
    record = await memory_service.store(
        context.db, content=content, source="agent", contact_id=contact_id
    )
    return ok(memory_id=record.id)


async def _send_whatsapp(context: ToolContext, to: str, message: str) -> str:
    # Deliver through the job queue so sends survive provider hiccups (retry).
    from jobs.service import JobService

    job = await JobService(context.db).enqueue(
        "whatsapp.send_text", {"to": to, "content": message}
    )
    return ok(queued=True, job_id=job.id)


find_contact_tool = Tool(
    name="find_contact",
    description="Busca um contato pelo nome ou telefone e retorna seu perfil e resumo.",
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
