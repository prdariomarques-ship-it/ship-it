import pytest


@pytest.mark.asyncio
async def test_task_crud(client, auth_headers):
    created = await client.post(
        "/api/tasks",
        json={"title": "Preparar culto", "priority": "high"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["status"] == "pending"

    updated = await client.patch(
        f"/api/tasks/{task_id}", json={"status": "done"}, headers=auth_headers
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "done"

    listed = await client.get("/api/tasks", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await client.delete(f"/api/tasks/{task_id}", headers=auth_headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/api/tasks/{task_id}", headers=auth_headers)).status_code == 404


@pytest.mark.asyncio
async def test_contact_crud(client, auth_headers):
    created = await client.post(
        "/api/contacts",
        json={"name": "João", "phone": "5511999999999", "categories": ["igreja"]},
        headers=auth_headers,
    )
    assert created.status_code == 201
    assert created.json()["categories"] == ["igreja"]

    count = await client.get("/api/contacts/count", headers=auth_headers)
    assert count.json() == {"count": 1}


@pytest.mark.asyncio
async def test_note_and_calendar_crud(client, auth_headers):
    note = await client.post(
        "/api/notes",
        json={"title": "Ideia", "content": "Automatizar avisos", "tags": ["igreja"]},
        headers=auth_headers,
    )
    assert note.status_code == 201

    event = await client.post(
        "/api/calendar",
        json={"title": "Culto", "starts_at": "2026-07-12T19:00:00Z"},
        headers=auth_headers,
    )
    assert event.status_code == 201
    assert event.json()["title"] == "Culto"


@pytest.mark.asyncio
async def test_church_and_store_crud(client, auth_headers):
    member = await client.post(
        "/api/church/members",
        json={"name": "Maria", "role": "louvor", "prayer_requests": ["saúde"]},
        headers=auth_headers,
    )
    assert member.status_code == 201

    customer = await client.post(
        "/api/store/customers",
        json={"name": "Cliente A", "email": "cliente@example.com"},
        headers=auth_headers,
    )
    assert customer.status_code == 201


@pytest.mark.asyncio
async def test_dashboard_summary(client, auth_headers):
    await client.post("/api/tasks", json={"title": "T1"}, headers=auth_headers)
    summary = await client.get("/api/dashboard/summary", headers=auth_headers)
    assert summary.status_code == 200
    assert summary.json()["pending_tasks"] == 1
