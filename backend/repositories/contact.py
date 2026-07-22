from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.contact import Contact
from repositories.base import SQLAlchemyRepository


class ContactRepository(SQLAlchemyRepository[Contact]):
    model = Contact

    async def get_by_phone(self, phone: str) -> Contact | None:
        return await self.find_one(phone=phone)

    async def get_or_create_by_phone(
        self, phone: str, name: str | None = None
    ) -> Contact:
        contact = await self.get_by_phone(phone)
        if contact is None:
            contact = Contact(name=name or phone, phone=phone)
            self.session.add(contact)
            try:
                await self.session.flush()
            except IntegrityError:
                # Concurrent webhooks for the same new phone: the other request
                # won the unique-constraint race — use its row.
                await self.session.rollback()
                contact = await self.get_by_phone(phone)
                if contact is None:
                    raise
        return contact

    async def search_by_name(self, query: str, limit: int = 5) -> list[Contact]:
        statement = select(Contact).where(Contact.name.ilike(f"%{query}%")).limit(limit)
        return list((await self.session.execute(statement)).scalars().all())

    async def list_for_intelligence(self, ceiling: int) -> list[Contact]:
        """Every contact, for the cross-contact priority ranking (see
        CONTACT_INTELLIGENCE_ARCHITECTURE.md #13). Scoring itself stays
        cheap regardless of address-book size -- it's 2 aggregate queries
        total (`TaskRepository.overdue_counts_by_contact`,
        `MessageRepository.last_message_by_contact`), not one per contact
        -- so unlike a "most recent N" pre-filter, this never silently
        drops a genuinely at-risk contact just because it hasn't been
        interacted with in a long time. `ceiling` (`Settings.
        contact_priority_candidate_ceiling`) is a safety bound against a
        pathologically large address book, not a ranking heuristic -- it
        is expected to never bind for this single-user system's realistic
        contact volume (see docs/CONTACTS.md)."""
        statement = select(Contact).order_by(Contact.id.asc()).limit(ceiling)
        return list((await self.session.execute(statement)).scalars().all())

    async def touch_last_interaction(self, contact: Contact, at: datetime) -> None:
        contact.last_interaction_at = at
        await self.session.commit()
