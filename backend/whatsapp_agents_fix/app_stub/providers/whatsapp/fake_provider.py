"""The actual point of this whole stub tree: a WhatsApp provider that
NEVER sends anything anywhere, just records every call it receives. The
test asserts on `.calls` to prove zero provider calls happened under each
blocking condition -- not a mock that merely returns a canned value, a
real object substituted at the one real boundary (the network call) that
must never fire for these scenarios."""


class FakeWhatsAppProvider:
    def __init__(self):
        self.calls: list[tuple] = []

    async def send_text(self, to, content, instance=None):
        self.calls.append(("send_text", to, content, instance))

    def reset(self):
        self.calls.clear()


FAKE_PROVIDER = FakeWhatsAppProvider()
