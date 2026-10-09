"""FAKE -- not exercised by send_whatsapp_text; present only so the
module-level import in jobs/handlers.py succeeds."""


class _FakeContactMemoryService:
    async def summarize_contact(self, db, contact_id):
        pass

    async def record_interaction(self, db, contact, text, source=None):
        return False


contact_memory_service = _FakeContactMemoryService()
