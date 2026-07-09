from datetime import datetime

from models.contact import Contact
from repositories.base import SQLAlchemyRepository


class ContactRepository(SQLAlchemyRepository[Contact]):
    model = Contact

    async def get_by_phone(self, phone: str) -> Contact | None:
        return await self.find_one(phone=phone)

    async def get_or_create_by_phone(self, phone: str, name: str | None = None) -> Contact:
        contact = await self.get_by_phone(phone)
        if contact is None:
            contact = Contact(name=name or phone, phone=phone)
            self.session.add(contact)
            await self.session.flush()
        return contact

    async def touch_last_interaction(self, contact: Contact, at: datetime) -> None:
        contact.last_interaction_at = at
        await self.session.commit()
