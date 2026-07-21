"""Built-in job handlers."""

from sqlalchemy.ext.asyncio import AsyncSession

from database.session import async_session_factory
from events.bus import Event, event_bus
from jobs.registry import job_handler
from jobs.service import JobService
from memory.contact_memory import contact_memory_service
from providers.mail.base import MailProviderError
from providers.mail.factory import get_mail_provider
from providers.whatsapp.factory import get_whatsapp_provider
from repositories.contact import ContactRepository
from repositories.email_account import EmailAccountRepository
from repositories.message import MessageRepository
from repositories.user import UserRepository
from services.audit import record_log
from services.messaging import persist_outbound_message
from services.token_crypto import decrypt_token
from utils.logging import get_logger
from workflows.service import workflow_service

logger = get_logger(__name__)

APOLOGY_MESSAGE = "Desculpe, tive um problema para responder agora. O Dario vai revisar sua mensagem em breve."


@job_handler("contact.summarize")
async def summarize_contact(db: AsyncSession, payload: dict) -> None:
    """Refresh a contact's automatic profile summary."""
    await contact_memory_service.summarize_contact(db, int(payload["contact_id"]))


@job_handler("memory.embed")
async def embed_interaction(db: AsyncSession, payload: dict) -> None:
    """Embed an interaction into the vector memory (off the message hot path)."""
    from memory.service import memory_service

    await memory_service.store(
        db,
        content=str(payload["content"]),
        source=str(payload.get("source", "whatsapp")),
        contact_id=payload.get("contact_id"),
    )


@job_handler("whatsapp.send_text")
async def send_whatsapp_text(db: AsyncSession, payload: dict) -> None:
    """Send a WhatsApp text through the configured provider (with queue retry),
    then persist it and feed the contact memory — same bookkeeping as the
    dashboard-triggered send, whether this was queued by the automatic reply
    or by an agent's send_whatsapp_message tool call."""
    to = str(payload["to"])
    content = str(payload["content"])
    await get_whatsapp_provider().send_text(to, content)
    await persist_outbound_message(db, to, content)


@job_handler("mail.send_reply")
async def send_mail_reply(db: AsyncSession, payload: dict) -> None:
    """Reply within an existing Gmail thread (queue retry covers a
    transient Gmail outage, same reasoning as whatsapp.send_text). Access
    token isn't cached anywhere -- refreshed fresh from the stored
    (encrypted) refresh token every time, same as agents/tools/mail.py's
    own _get_access_token."""
    user_id = int(payload["user_id"])
    thread_id = str(payload["thread_id"])

    provider = get_mail_provider()
    account = await EmailAccountRepository(db).get_by_user(user_id, provider.name)
    if account is None:
        logger.error("mail.send_reply: no email account for user %s", user_id)
        return
    refresh_token = decrypt_token(account.encrypted_refresh_token)
    tokens = await provider.refresh_access_token(refresh_token)

    try:
        message_id = await provider.send_reply(
            tokens.access_token,
            thread_id=thread_id,
            to=list(payload["to"]),
            subject=str(payload["subject"]),
            body=str(payload["body"]),
            in_reply_to_message_id=payload.get("in_reply_to_message_id"),
        )
    except MailProviderError:
        raise  # let the job queue's own retry/backoff handle a transient failure

    await record_log(
        db,
        source=f"mail:reply:{user_id}",
        message=f"Email reply sent in thread {thread_id}",
        level="info",
        payload={"thread_id": thread_id, "message_id": message_id},
    )


@job_handler("workflow.trigger")
async def trigger_workflow(db: AsyncSession, payload: dict) -> None:
    """Fire an n8n workflow; queue retries cover transient n8n outages."""
    await workflow_service.trigger(
        str(payload["workflow"]), dict(payload.get("data", {}))
    )


@job_handler("whatsapp.process_inbound")
async def process_inbound_whatsapp_message(db: AsyncSession, payload: dict) -> None:
    """The automatic end-to-end reply: the Cognitive Pipeline (Fase 4.2)
    classifies intent/priority, plans, picks the agent(s), runs them (memory
    + tools), validates the result, and updates memory — then the reply is
    queued back through the existing whatsapp.send_text job, so sending
    inherits the same retry as everything else. This is the piece that makes
    the WhatsApp flow work without n8n.
    """
    from orchestrator.pipeline import cognitive_pipeline

    contact_id = int(payload["contact_id"])
    message_id = int(payload["message_id"])

    contact = await ContactRepository(db).get(contact_id)
    message = await MessageRepository(db).get(message_id)
    owner = await UserRepository(db).get_first_admin()
    if contact is None or message is None or owner is None or not contact.phone:
        logger.warning(
            "Skipping auto-reply: contact=%s message=%s owner=%s",
            contact_id,
            message_id,
            owner is not None,
        )
        return

    result = await cognitive_pipeline.process(
        db=db, user=owner, message=message.content, contact_id=contact.id
    )

    if result.reply.strip():
        await JobService(db).enqueue(
            "whatsapp.send_text", {"to": contact.phone, "content": result.reply}
        )


def register_event_subscribers() -> None:
    """Wire the handlers above into the Event Bus. Called explicitly from the
    app's startup (not a bare module-level side effect), so tests can
    re-arm this subscription after the per-test event bus reset."""
    event_bus.subscribe("job.failed", _apologize_after_failed_auto_reply)


async def _apologize_after_failed_auto_reply(event: Event) -> None:
    """Safety net: if the automatic-reply job exhausts its retries, don't
    leave the contact in silence — send a short apology instead. Demonstrates
    the Event Bus doing real work: this handler has no direct coupling to the
    job worker or the webhook, it only reacts to `job.failed`.
    """
    if event.payload.get("job_name") != "whatsapp.process_inbound":
        return

    job_payload = event.payload.get("job_payload") or {}
    contact_id = job_payload.get("contact_id")
    if contact_id is None:
        return

    async with async_session_factory() as session:
        contact = await ContactRepository(session).get(int(contact_id))
        if contact is None or not contact.phone:
            return
        await JobService(session).enqueue(
            "whatsapp.send_text", {"to": contact.phone, "content": APOLOGY_MESSAGE}
        )
