"""FAKE persist_outbound_message -- records calls, no real persistence."""

PERSIST_CALLS: list[dict] = []


async def persist_outbound_message(db, to, content, is_autopilot_reply=False, instance=None):
    PERSIST_CALLS.append({"to": to, "content": content, "is_autopilot_reply": is_autopilot_reply, "instance": instance})
