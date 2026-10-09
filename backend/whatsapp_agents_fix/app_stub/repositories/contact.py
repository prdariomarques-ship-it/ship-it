"""FAKE -- not exercised by the send_whatsapp_text scenarios in this
round (they all use a non-personal instance, so _owner_audio_send_guard
short-circuits before ever touching a repository). Raises loudly instead
of silently returning something plausible if that assumption is wrong."""


class ContactRepository:
    def __init__(self, db):
        self.db = db

    async def get(self, contact_id):
        raise NotImplementedError("ContactRepository.get was reached -- the test's non-personal-instance assumption is wrong")
