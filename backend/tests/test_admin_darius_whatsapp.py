"""Read-only admin views of the WhatsApp -> DARIUS flow: access control, filters, paging, secrecy, routing state."""
from __future__ import annotations

import json

import pytest

from admin.darius import operator_client  # noqa: F401 -- imported for parity with the bridge tests
from models.contact import Contact
from models.darius_whatsapp_task import FAILED, REPLY_QUEUED, SUBMITTED, DariusWhatsAppTask
from models.message import Message, MessageDirection, MessageMediaType
from services import automation_suspension
from tests.test_admin_darius import admin_headers, admin_user, session_factory, user_headers  # noqa: F401
from utils.config import get_settings

PREFIX = "/api/admin/darius"
SECRET_TEXT = "texto-secreto-do-cliente-123"


@pytest.fixture
def configured(monkeypatch):
    s = get_settings()
    for key, value in {
        "darius_whatsapp_enabled": True, "darius_whatsapp_instances": "store,ghost",
        "automation_suspended": False, "evolution_instance": "store", "evolution_personal_instance": "personal",
        "line_watch_instances": "", "evolution_media_extra_instances": "",
        "darius_base_url": "http://darius.test", "darius_api_token": "service-token-0123456789",
    }.items():
        monkeypatch.setattr(s, key, value)
    return s


async def _seed(session_factory) -> list[int]:
    ids: list[int] = []
    async with session_factory() as db:
        contact = Contact(name="Cliente", phone="5511999990001", preferences={})
        db.add(contact)
        await db.flush()
        for n, (instance, status, task_id) in enumerate(
            [("store", REPLY_QUEUED, "t-1"), ("store", FAILED, "t-2"), ("personal", SUBMITTED, "t-3")], start=1
        ):
            message = Message(
                contact_id=contact.id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT,
                content=SECRET_TEXT, whatsapp_instance=instance, external_id=f"W{n}",
            )
            db.add(message)
            await db.flush()
            link = DariusWhatsAppTask(
                dedupe_key=f"k{n}", message_id=message.id, contact_id=contact.id, instance=instance, status=status,
                darius_task_id=task_id, darius_status="COMPLETED", attempts=1, reply_chars=42,
                history=[{"kind": status}], last_error="boom" if status == FAILED else None,
            )
            db.add(link)
            await db.flush()
            ids.append(link.id)
        await db.commit()
    return ids


@pytest.mark.parametrize("path", ["/whatsapp-tasks", "/whatsapp-routing"])
async def test_requires_authentication_and_admin(client, user_headers, path):  # noqa: F811
    assert (await client.get(PREFIX + path)).status_code == 401
    assert (await client.get(PREFIX + path, headers=user_headers)).status_code == 403


async def test_empty_list_has_no_items_and_no_counts(client, admin_headers):  # noqa: F811
    body = (await client.get(PREFIX + "/whatsapp-tasks", headers=admin_headers)).json()
    assert body == {"items": [], "counts": {}, "next_offset": None}


async def test_lists_links_newest_first_with_counts_and_never_exposes_conversation_text(
    client, admin_headers, session_factory,  # noqa: F811
):
    await _seed(session_factory)
    response = await client.get(PREFIX + "/whatsapp-tasks", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert [i["darius_task_id"] for i in body["items"]] == ["t-3", "t-2", "t-1"]
    assert body["counts"] == {"reply_queued": 1, "failed": 1, "submitted": 1}
    assert body["next_offset"] is None
    assert SECRET_TEXT not in json.dumps(body)
    assert all("content" not in item and "phone" not in item and "dedupe_key" not in item for item in body["items"])
    failed = next(i for i in body["items"] if i["status"] == "failed")
    assert failed["last_error"] == "boom" and failed["history"] == [{"kind": "failed"}]


async def test_filters_by_status_and_instance_and_pages(client, admin_headers, session_factory):  # noqa: F811
    await _seed(session_factory)
    by_status = (await client.get(PREFIX + "/whatsapp-tasks?status=failed", headers=admin_headers)).json()
    assert [i["darius_task_id"] for i in by_status["items"]] == ["t-2"]
    by_instance = (await client.get(PREFIX + "/whatsapp-tasks?instance=store", headers=admin_headers)).json()
    assert {i["darius_task_id"] for i in by_instance["items"]} == {"t-1", "t-2"}
    assert by_instance["counts"]["submitted"] == 1               # counts are global, not filtered

    first = (await client.get(PREFIX + "/whatsapp-tasks?limit=2", headers=admin_headers)).json()
    assert [i["darius_task_id"] for i in first["items"]] == ["t-3", "t-2"] and first["next_offset"] == 2
    second = (await client.get(PREFIX + "/whatsapp-tasks?limit=2&offset=2", headers=admin_headers)).json()
    assert [i["darius_task_id"] for i in second["items"]] == ["t-1"] and second["next_offset"] is None


@pytest.mark.parametrize("query", ["status=bogus", "limit=0", "limit=201", "offset=-1"])
async def test_rejects_invalid_query(client, admin_headers, query):  # noqa: F811
    assert (await client.get(PREFIX + f"/whatsapp-tasks?{query}", headers=admin_headers)).status_code == 422


async def test_routing_reports_each_configured_instance_and_unknown_routed_ones(
    client, admin_headers, session_factory, configured,  # noqa: F811
):
    async with session_factory() as db:
        await automation_suspension.set_instance(db, configured, "personal", True, 1, "manutencao do numero")
    body = (await client.get(PREFIX + "/whatsapp-routing", headers=admin_headers)).json()
    assert body["enabled"] is True and body["darius_configured"] is True
    assert body["global_suspended"] is False and body["global_suspension_reason"] is None
    by_name = {i["instance"]: i for i in body["instances"]}
    assert by_name["store"] == {"instance": "store", "routed_to_darius": True, "suspended": False, "suspension_reason": None}
    assert by_name["personal"]["routed_to_darius"] is False and by_name["personal"]["suspended"] is True
    assert by_name["personal"]["suspension_reason"] == "manutencao do numero"
    assert body["unknown_routed_instances"] == ["ghost"]          # routed in config but not a configured instance


async def test_routing_is_all_off_when_the_flag_is_off_and_reports_global_suspension(
    client, admin_headers, session_factory, configured, monkeypatch,  # noqa: F811
):
    monkeypatch.setattr(configured, "darius_whatsapp_enabled", False)
    monkeypatch.setattr(configured, "darius_api_token", "")
    async with session_factory() as db:
        await automation_suspension.set_global(db, configured, True, 1, "incidente")
    body = (await client.get(PREFIX + "/whatsapp-routing", headers=admin_headers)).json()
    assert body["enabled"] is False and body["darius_configured"] is False
    assert not any(i["routed_to_darius"] for i in body["instances"])
    assert body["global_suspended"] is True and body["global_suspension_reason"] == "incidente"


async def test_link_timestamps_are_timezone_aware_even_when_the_driver_drops_tzinfo(
    client, admin_headers, session_factory,  # noqa: F811
):
    """SQLite hands back naive datetimes for timestamptz columns; the browser would read them as local time."""
    from datetime import datetime

    await _seed(session_factory)
    items = (await client.get(PREFIX + "/whatsapp-tasks", headers=admin_headers)).json()["items"]
    assert items
    for item in items:
        assert datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")).utcoffset() is not None