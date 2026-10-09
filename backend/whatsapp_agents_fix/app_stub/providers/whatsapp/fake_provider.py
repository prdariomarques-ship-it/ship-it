"""The actual point of this whole stub tree: a WhatsApp provider that
NEVER sends anything anywhere, just records every call it receives. The
test asserts on `.calls` to prove zero provider calls happened under each
blocking condition -- not a mock that merely returns a canned value, a
real object substituted at the one real boundary (the network call) that
must never fire for these scenarios."""


class FakeWhatsAppProvider:
    def __init__(self):
        self.calls: list[tuple] = []
        # Review fix (C): a real send returns a dict with the provider's
        # own message id at response["key"]["id"] (Baileys/Evolution API
        # shape) -- this default simulates that so tests can prove a
        # successful send is actually promoted to 'sent', not just that
        # the call happened. Set to None (via `simulated_response`) to
        # simulate an uncertain/unrecognized provider response instead.
        self.simulated_response: dict | None = {"key": {"id": "FAKE-RECEIPT-1"}}

    async def send_text(self, to, content, instance=None):
        self.calls.append(("send_text", to, content, instance))
        return self.simulated_response

    def reset(self):
        self.calls.clear()
        self.simulated_response = {"key": {"id": "FAKE-RECEIPT-1"}}


FAKE_PROVIDER = FakeWhatsAppProvider()
