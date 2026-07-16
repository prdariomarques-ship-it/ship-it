"""Shared outbound-message bookkeeping: persist + feed the contact memory.

Two call sites need the exact same side effects after a WhatsApp send
succeeds — the dashboard-triggered endpoints (api/whatsapp.py) and the
job-triggered send used by the automatic reply and by agent tools
(jobs/handlers.py). Before this existed, only the API path persisted the
message and fed memory; the job path silently skipped both. This is the one
place that does it, so neither path can drift from the other again.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from jobs.service import JobService
from memory.contact_memory import contact_memory_service
from models.message import Message, MessageDirection, MessageMediaType
from providers.whatsapp.base import normalize_phone
from repositories.contact import ContactRepository


async def persist_outbound_message(
    db: AsyncSession,
    phone: str,
    content: str,
    media_type: MessageMediaType = MessageMediaType.TEXT,
) -> Message:
    """Record an outbound WhatsApp message and feed the contact memory.

    Call this AFTER the provider send succeeds — never before, so a failed
    send doesn't leave a message row claiming something was delivered.
    """
    clean_phone = normalize_phone(phone)
    contact = await ContactRepository(db).get_or_create_by_phone(clean_phone)

    message = Message(
        contact_id=contact.id,
        direction=MessageDirection.OUTBOUND,
        media_type=media_type,
        content=content,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    summary_due = await contact_memory_service.record_interaction(
        db, contact, content, source="whatsapp"
    )
    if summary_due:
        await JobService(db).enqueue("contact.summarize", {"contact_id": contact.id})
    return message
