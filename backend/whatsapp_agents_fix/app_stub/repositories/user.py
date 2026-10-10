"""FAKE -- not exercised by send_whatsapp_text at all (only by
twin_autopilot_check, which this test file does not call)."""


class UserRepository:
    def __init__(self, db):
        self.db = db

    async def get_first_admin(self):
        raise NotImplementedError("UserRepository.get_first_admin was reached")
