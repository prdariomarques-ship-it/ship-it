"""Memory Manager: the single facade every caller uses to read or write memory.

Four kinds of memory live behind one API, so agents and tools never need to
know which store backs which kind:

- **short-term**  — the recent conversation transcript (Postgres, via
  `MessageRepository`)
- **long-term**   — semantic search over past interactions (Qdrant, via
  `MemoryService`)
- **knowledge**    — semantic search over ingested documents/facts (same
  Qdrant collection, tagged `source="knowledge"`; the ingestion pipeline
  itself — summarizing and vectorizing uploaded documents — is a Phase 4
  feature, but this read surface is ready for it today)
- **preferences** — structured per-contact settings (`Contact.preferences`,
  modeled from day one but never exposed through a manager or a tool until
  now)

This is a Facade over already-tested components (`MemoryService`,
`ContactMemoryService`, the repositories) — it composes, it doesn't
reimplement. Nothing outside `memory/` talks to Qdrant or the Contact model's
memory fields directly anymore.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from memory.contact_memory import contact_memory_service
from memory.service import memory_service
from models.message import Message
from repositories.contact import ContactRepository
from repositories.message import MessageRepository

KNOWLEDGE_SOURCE = "knowledge"


class MemoryManager:
    """Facade unifying short-term, long-term, knowledge and preference memory."""

    async def short_term(self, db: AsyncSession, contact_id: int, limit: int = 20) -> list[Message]:
        """Recent conversation transcript for a contact, oldest first."""
        return await MessageRepository(db).recent_for_contact(contact_id, limit=limit)

    async def long_term_search(
        self, query: str, contact_id: int | None = None, limit: int = 5
    ) -> list[dict]:
        """Semantic search over past interactions (optionally scoped to one contact)."""
        return await memory_service.search(query=query, limit=limit, contact_id=contact_id)

    async def knowledge_search(self, query: str, limit: int = 5) -> list[dict]:
        """Semantic search over ingested knowledge (documents, facts, policies).

        Ingestion (upload -> summarize -> vectorize -> tag as knowledge) is
        not built yet; anything stored with `source=KNOWLEDGE_SOURCE` is
        already searchable through this method.
        """
        # Over-fetch then filter by tag: the Qdrant client version in use has
        # no server-side payload filter combinator for this collection yet.
        results = await memory_service.search(query=query, limit=max(limit * 4, 20))
        return [item for item in results if item.get("source") == KNOWLEDGE_SOURCE][:limit]

    async def remember(
        self, db: AsyncSession, content: str, source: str, contact_id: int | None = None
    ) -> int:
        """Embed and store a memory synchronously; returns the stored record id.

        For explicit, user-triggered saves (e.g. the `store_memory` tool)
        where the caller wants immediate confirmation. High-volume,
        latency-sensitive paths (every inbound/outbound WhatsApp message)
        should go through the durable queue instead — see
        `ContactMemoryService.record_interaction`, which enqueues
        `memory.embed` rather than calling this synchronously.
        """
        record = await memory_service.store(db, content=content, source=source, contact_id=contact_id)
        return record.id

    async def get_preferences(self, db: AsyncSession, contact_id: int) -> dict:
        contact = await ContactRepository(db).get(contact_id)
        return dict(contact.preferences) if contact else {}

    async def get_summary(self, db: AsyncSession, contact_id: int) -> str | None:
        """The AI-maintained profile summary (`ContactMemoryService.summarize_contact`)."""
        contact = await ContactRepository(db).get(contact_id)
        return contact.summary if contact else None

    async def add_categories(self, db: AsyncSession, contact_id: int, categories: list[str]) -> list[str]:
        """Merge new categories into a contact's tags; skips ones already
        present so learning never writes the same fact twice. Returns only
        the categories that were actually new."""
        repository = ContactRepository(db)
        contact = await repository.get(contact_id)
        if contact is None:
            return []
        new_ones = [category for category in categories if category not in contact.categories]
        if not new_ones:
            return []
        await repository.update(contact, categories=[*contact.categories, *new_ones])
        return new_ones

    async def set_preference(self, db: AsyncSession, contact_id: int, key: str, value: object) -> dict:
        """Merge one preference into the contact's preferences; returns the full dict."""
        repository = ContactRepository(db)
        contact = await repository.get(contact_id)
        if contact is None:
            raise ValueError(f"Contact {contact_id} not found")
        preferences = {**contact.preferences, key: value}
        await repository.update(contact, preferences=preferences)
        return preferences

    async def build_agent_context(self, query: str, contact_id: int | None) -> dict:
        """Everything an agent should see before answering: relevant long-term memories."""
        return await contact_memory_service.build_context(query, contact_id)


memory_manager = MemoryManager()
