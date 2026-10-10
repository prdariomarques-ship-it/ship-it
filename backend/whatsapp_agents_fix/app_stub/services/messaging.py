"""FAKE persist_outbound_message -- records calls, no real persistence.

Honors the real function's return contract (a Message with contact_id and
whatsapp_instance), since jobs/handlers.py's send_whatsapp_text depends on
it to scope the receipt it records. The contact id is the fixture's known
contact (see conftest.py's real_control_db), not a real lookup by phone.
"""

from types import SimpleNamespace

PERSIST_CALLS: list[dict] = []


async def persist_outbound_message(db, to, content, is_autopilot_reply=False, instance=None):
    PERSIST_CALLS.append({"to": to, "content": content, "is_autopilot_reply": is_autopilot_reply, "instance": instance})
    return SimpleNamespace(contact_id=42, whatsapp_instance=instance)
