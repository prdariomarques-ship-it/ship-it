"""Per-contact memory: history embeddings, automatic summary, last interaction.

Every inbound/outbound message becomes an embedding tied to the contact; every
N messages a background job asks the LLM to refresh the contact's profile
summary. Preferences and tags live on the Contact row and are injected into
agent context alongside semantic search results.
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from memory.service import memory_service
from models.contact import Contact
from providers.llm.base import ChatMessage
from providers.llm.factory import get_llm_provider
from repositories.contact import ContactRepository
from repositories.message import MessageRepository
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

SUMMARY_PROMPT = (
    "Você mantém o perfil de um contato no Dario OS. A partir do histórico de "
    "mensagens abaixo, escreva um resumo conciso (máximo 5 frases) sobre quem é "
    "essa pessoa, o que costuma tratar e qualquer preferência relevante. "
    "Responda apenas com o resumo, em português brasileiro."
)


class ContactMemoryService:
    """Application service coordinating Contact rows, Qdrant and the LLM."""

    def __init__(self) -> None:
        self._settings = get_settings()

    async def record_interaction(
        self, db: AsyncSession, contact: Contact, content: str, source: str
    ) -> bool:
        """Touch last_interaction_at and queue the embedding for the worker.

        Embedding needs two external calls (LLM + Qdrant); doing it inline would
        put third-party latency on the message hot path, so it goes through the
        durable queue (which also gives it retry for free).

        Returns True when the contact is due for a summary refresh.
        """
        from jobs.service import JobService

        contacts = ContactRepository(db)
        await contacts.touch_last_interaction(contact, datetime.now(timezone.utc))

        if content.strip():
            await JobService(db).enqueue(
                "memory.embed",
                {"content": content, "source": source, "contact_id": contact.id},
            )

        messages = MessageRepository(db)
        total = await messages.count(contact_id=contact.id)
        every = self._settings.contact_summary_every_n_messages
        return total > 0 and total % every == 0

    async def summarize_contact(self, db: AsyncSession, contact_id: int) -> str | None:
        """Regenerate the contact's automatic profile summary from recent history."""
        contacts = ContactRepository(db)
        contact = await contacts.get(contact_id)
        if contact is None:
            return None

        history = await MessageRepository(db).recent_for_contact(contact_id, limit=30)
        if not history:
            return None

        transcript = "\n".join(
            f"[{message.direction.value}] {message.content}" for message in history if message.content
        )
        result = await get_llm_provider().chat(
            [
                ChatMessage(role="system", content=SUMMARY_PROMPT),
                ChatMessage(role="user", content=f"Contato: {contact.name}\n\nHistórico:\n{transcript}"),
            ]
        )
        summary = result.content.strip()
        if summary:
            await contacts.update(contact, summary=summary)
        return summary or None

    async def build_context(self, query: str, contact_id: int | None) -> dict:
        """Everything an agent should know: profile + relevant memories."""
        memories = await memory_service.search(query=query, limit=5, contact_id=contact_id)
        return {"memories": memories}


contact_memory_service = ContactMemoryService()
