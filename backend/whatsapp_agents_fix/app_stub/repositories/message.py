"""FAKE -- see repositories/contact.py's docstring."""


class MessageRepository:
    def __init__(self, db):
        self.db = db

    async def get(self, message_id):
        raise NotImplementedError("MessageRepository.get was reached -- the test's non-personal-instance assumption is wrong")

    async def recent_for_contact(self, contact_id, limit=15, instance=None):
        raise NotImplementedError("MessageRepository.recent_for_contact was reached")

    async def get_latest_inbound(self, contact_id, instance=None):
        raise NotImplementedError("MessageRepository.get_latest_inbound was reached")

    async def find_unacknowledged_outbound(self, contact_id, text, instance=None, within_seconds=None):
        raise NotImplementedError("MessageRepository.find_unacknowledged_outbound was reached -- load the real repositories.message module for any test exercising webhooks/router.py's text-reply/echo path")
