"""Google Contacts tools — Sprint 2. Read+write: search/list (covers
"listar", "buscar", "localizar telefone", "localizar e-mail" — a query
matches name, email or phone, mirroring how Gmail's `search_emails`
consolidates multiple filters into one tool instead of one per filter),
create, update, delete.

Registered only on `agents/assistant_agent.py`. No other agent gets these —
the Contacts domain has exactly one technical gateway, same as Email and
Calendar. A specialized agent that needs something from the address book
gets it through a Cognitive Planner multi-step plan that routes one step to
`assistant`, never through direct tool access — see `docs/CONTACTS.md`.

These tools operate on the user's *Google* Contacts (People API) address
book — unrelated to Dario OS's own internal `find_contact`/`send_whatsapp_message`
tools (`agents/tools/communication.py`, backed by `models.contact.Contact`,
the WhatsApp-conversation contact book with its own PROD-005 isolation).
Neither domain reads or writes the other's data.
"""

from agents.tools.base import Tool, ToolContext, ok
from providers.contacts.base import (
    ContactsProviderError,
    ContactSearchQuery,
    ContactUpdate,
    NewContact,
)
from providers.contacts.factory import get_contacts_provider
from repositories.gcontacts_account import GoogleContactsAccountRepository
from services.token_crypto import TokenEncryptionNotConfigured, decrypt_token


class ContactsNotConnectedError(RuntimeError):
    """No Google Contacts authorized for this user — surfaced to the model
    as a normal tool error (via Tool.run's catch-all), same as any other
    tool failure. Never a crash, never a fallback to someone else's address
    book."""


async def _get_access_token(context: ToolContext) -> str:
    """The only place a Google Contacts account is chosen — always from
    `context.user.id` (set by the application, never by the model). Same
    principle as `agents/tools/mail.py`/`agents/tools/gcalendar.py`."""
    if context.user is None:
        raise ContactsNotConnectedError("No authenticated user in context")

    provider = get_contacts_provider()
    account = await GoogleContactsAccountRepository(context.db).get_by_user(
        context.user.id, provider.name
    )
    if account is None:
        raise ContactsNotConnectedError(
            "Nenhum Google Contacts conectado. Peça ao administrador para conectar em /api/gcontacts/connect."
        )
    try:
        refresh_token = decrypt_token(account.encrypted_refresh_token)
    except TokenEncryptionNotConfigured as exc:
        raise ContactsNotConnectedError(str(exc)) from exc

    try:
        tokens = await provider.refresh_access_token(refresh_token)
    except ContactsProviderError as exc:
        raise ContactsNotConnectedError(
            "A conexão com o Google Contacts expirou ou foi revogada. Peça ao administrador para "
            "reconectar em /api/gcontacts/connect."
        ) from exc
    return tokens.access_token


def _contact_to_dict(contact) -> dict:
    return {
        "resource_name": contact.resource_name,
        "display_name": contact.display_name,
        "given_name": contact.given_name,
        "family_name": contact.family_name,
        "emails": contact.emails,
        "phones": contact.phones,
    }


async def _search_contacts(
    context: ToolContext, query: str | None = None, limit: int = 50
) -> str:
    access_token = await _get_access_token(context)
    provider = get_contacts_provider()
    try:
        contacts = await provider.search_contacts(
            access_token, ContactSearchQuery(query=query, limit=min(limit, 200))
        )
    except ContactsProviderError as exc:
        raise RuntimeError(f"Falha ao buscar contatos: {exc}") from exc
    return ok(contacts=[_contact_to_dict(c) for c in contacts])


async def _create_contact(
    context: ToolContext,
    given_name: str,
    family_name: str = "",
    emails: list[str] | None = None,
    phones: list[str] | None = None,
) -> str:
    access_token = await _get_access_token(context)
    provider = get_contacts_provider()
    new_contact = NewContact(
        given_name=given_name,
        family_name=family_name,
        emails=emails or [],
        phones=phones or [],
    )
    try:
        contact = await provider.create_contact(access_token, new_contact)
    except ContactsProviderError as exc:
        raise RuntimeError(f"Falha ao criar contato: {exc}") from exc
    return ok(contact=_contact_to_dict(contact))


async def _update_contact(
    context: ToolContext,
    resource_name: str,
    given_name: str | None = None,
    family_name: str | None = None,
    emails: list[str] | None = None,
    phones: list[str] | None = None,
) -> str:
    access_token = await _get_access_token(context)
    provider = get_contacts_provider()
    update = ContactUpdate(
        given_name=given_name, family_name=family_name, emails=emails, phones=phones
    )
    try:
        contact = await provider.update_contact(access_token, resource_name, update)
    except ContactsProviderError as exc:
        raise RuntimeError(f"Falha ao editar contato: {exc}") from exc
    return ok(contact=_contact_to_dict(contact))


async def _delete_contact(context: ToolContext, resource_name: str) -> str:
    access_token = await _get_access_token(context)
    provider = get_contacts_provider()
    try:
        await provider.delete_contact(access_token, resource_name)
    except ContactsProviderError as exc:
        raise RuntimeError(f"Falha ao remover contato: {exc}") from exc
    return ok(deleted=True, resource_name=resource_name)


search_google_contacts_tool = Tool(
    name="search_google_contacts",
    description=(
        "Busca ou lista contatos do Google Contacts por nome, telefone ou e-mail. Sem `query`, lista "
        "todos os contatos. Use para 'localizar telefone de X' ou 'localizar e-mail de X'."
    ),
    handler=_search_contacts,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Nome, telefone ou e-mail (parcial) do contato",
            },
            "limit": {
                "type": "integer",
                "description": "Máximo de resultados (padrão 50)",
            },
        },
        "required": [],
    },
)

create_google_contact_tool = Tool(
    name="create_google_contact",
    description="Cria um novo contato no Google Contacts.",
    handler=_create_contact,
    parameters={
        "type": "object",
        "properties": {
            "given_name": {"type": "string"},
            "family_name": {"type": "string"},
            "emails": {"type": "array", "items": {"type": "string"}},
            "phones": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["given_name"],
    },
)

update_google_contact_tool = Tool(
    name="update_google_contact",
    description="Edita um contato existente do Google Contacts (só os campos informados mudam).",
    handler=_update_contact,
    parameters={
        "type": "object",
        "properties": {
            "resource_name": {
                "type": "string",
                "description": "Id do contato (ex: 'people/c123...')",
            },
            "given_name": {"type": "string"},
            "family_name": {"type": "string"},
            "emails": {"type": "array", "items": {"type": "string"}},
            "phones": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["resource_name"],
    },
)

delete_google_contact_tool = Tool(
    name="delete_google_contact",
    description="Remove um contato do Google Contacts.",
    handler=_delete_contact,
    parameters={
        "type": "object",
        "properties": {
            "resource_name": {
                "type": "string",
                "description": "Id do contato (ex: 'people/c123...')",
            }
        },
        "required": ["resource_name"],
    },
)
