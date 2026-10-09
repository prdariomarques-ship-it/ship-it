"""FAKE -- not exercised by the send_whatsapp_text scenarios in this
round (they all use a non-personal instance, so _owner_audio_send_guard
short-circuits before ever touching a repository). Raises loudly instead
of silently returning something plausible if that assumption is wrong."""


class ContactRepository:
    def __init__(self, db):
        self.db = db

    async def get(self, contact_id):
        raise NotImplementedError("ContactRepository.get was reached -- the test's non-personal-instance assumption is wrong")

    async def get_or_create_by_phone(self, phone):
        # FAKE, for test_persist_outbound_message_real_execution.py's
        # review fix (C) coverage only -- a lightweight stand-in with just
        # the `.id` the real persist_outbound_message needs to set
        # Message.contact_id. Not persisted; the test's SQLite connection
        # doesn't enforce foreign keys by default, so this is sufficient
        # to prove the Message row itself is built correctly.
        class _FakeContact:
            id = 1

        return _FakeContact()
