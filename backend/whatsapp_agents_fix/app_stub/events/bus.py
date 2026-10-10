"""FAKE -- jobs/handlers.py imports Event/event_bus at module level to
register event subscribers; not exercised by send_whatsapp_text itself."""


class Event:
    def __init__(self, name=None, payload=None):
        self.name = name
        self.payload = payload or {}


class _FakeEventBus:
    def subscribe(self, event_name, handler):
        pass


event_bus = _FakeEventBus()
