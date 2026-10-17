import pytest

from zervis_bridge.sanitize import sanitize_event


def event(name, payload, at="2026-10-17T10:00:00+00:00"):
    return {"name": name, "payload": payload, "occurred_at": at}


def test_job_event_drops_phone_and_job_payload():
    safe = sanitize_event(
        event(
            "job.failed",
            {
                "job_id": 7,
                "job_name": "send_whatsapp",
                "attempts": 3,
                "status": "failed",
                "detail": "timeout",
                "job_payload": {"phone": "+5511999990000", "contact_id": 4},
            },
        )
    )
    assert safe["payload"] == {
        "job_id": 7,
        "job_name": "send_whatsapp",
        "attempts": 3,
        "status": "failed",
        "detail": "timeout",
    }
    assert "5511" not in str(safe)


def test_message_received_keeps_only_the_fact():
    safe = sanitize_event(
        event(
            "whatsapp.message_received",
            {"contact_id": 1, "message_id": 2, "phone": "+5511", "provider": "openwa"},
        )
    )
    assert safe["payload"] == {"provider": "openwa"}


def test_agent_events_never_carry_contact_or_user_ids():
    safe = sanitize_event(
        event(
            "agent.replied",
            {"agent": "store", "contact_id": 9, "user_id": 1, "cost_usd": 0.01},
        )
    )
    assert safe["payload"] == {"agent": "store", "cost_usd": 0.01}


@pytest.mark.parametrize(
    "name", ["admin.setting_updated", "admin.job_cancelled", "unknown.thing", "x"]
)
def test_events_outside_the_allowlist_are_dropped(name):
    assert (
        sanitize_event(event(name, {"key": "OPENAI_API_KEY", "value": "sk-secret"}))
        is None
    )


def test_wildcard_domain_covers_new_job_and_goal_events():
    assert sanitize_event(event("job.some_new_state", {"job_id": 1}))["payload"] == {
        "job_id": 1
    }
    assert sanitize_event(event("goal.blocked", {"goal_id": 1, "user_id": 5}))[
        "payload"
    ] == {"goal_id": 1}


def test_nested_objects_and_long_strings_are_neutralised():
    safe = sanitize_event(
        event(
            "job.failed",
            {"detail": "x" * 1000, "status": {"nested": "no"}, "job_id": 1},
        )
    )
    assert safe["payload"] == {"detail": "x" * 200, "job_id": 1}


def test_list_fields_keep_only_scalars():
    safe = sanitize_event(
        event(
            "observation.context_updated",
            {
                "degraded_sources": ["calendar", {"a": 1}],
                "item_count": 3,
                "trigger": "tick",
            },
        )
    )
    assert safe["payload"]["degraded_sources"] == ["calendar"]


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "x",
        [],
        {"name": 1},
        {"name": "job.x"},
        {"name": "job.x", "occurred_at": 5},
    ],
)
def test_malformed_events_are_dropped(raw):
    assert sanitize_event(raw) is None


def test_payload_not_a_mapping_yields_empty_payload():
    assert sanitize_event(event("job.done", "oops"))["payload"] == {}
