"""GET .../workspace recommendations + POST .../recommendations/{id}/execute
-- Release 1.5, P0-4.

Integration coverage for the wiring `test_contact_recommendations.py`
doesn't reach: the endpoint actually populating `recommendations` from
live signals, and the execute endpoint actually dispatching through the
Tool Registry (never the Cognitive Planner) and recording an audit log
entry. Recommendation content/tie-break correctness itself is unit-
tested in `test_contact_recommendations.py`, no DB.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.contact import Contact
from models.log import LogEntry
from models.task import Task, TaskPriority, TaskStatus
from models.user import User
from utils import messages as user_messages


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _register_and_login(client) -> dict[str, str]:
    await client.post(
        "/api/auth/register",
        json={
            "email": "recommendations@example.com",
            "full_name": "Owner",
            "password": "supersecret1",
        },
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "recommendations@example.com", "password": "supersecret1"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _owner_user(session_factory) -> User:
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == "recommendations@example.com")
        )
        return result.scalar_one()


async def _new_contact(session_factory, **kwargs) -> Contact:
    async with session_factory() as session:
        contact = Contact(**kwargs)
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


# --- GET .../workspace populates recommendations ---------------------------------------
@pytest.mark.asyncio
async def test_workspace_recommendations_reflect_live_signals(client, session_factory):
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(session_factory, name="Contato com pendência")
    async with session_factory() as session:
        session.add(
            Task(
                user_id=owner.id,
                title="Atrasada",
                contact_id=contact.id,
                status=TaskStatus.PENDING,
                priority=TaskPriority.HIGH,
                due_date=datetime.now(timezone.utc) - timedelta(days=5),
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    body = response.json()
    recommendations = body["recommendations"]
    assert len(recommendations) == 1
    assert recommendations[0]["type"] == "check_pending_tasks"
    assert recommendations[0]["confirmation_required"] is False


@pytest.mark.asyncio
async def test_workspace_recommendations_empty_for_healthy_contact(
    client, session_factory
):
    headers = await _register_and_login(client)
    contact = await _new_contact(
        session_factory,
        name="Saudável",
        last_interaction_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    assert response.json()["recommendations"] == []


# --- POST .../recommendations/{id}/execute ----------------------------------------------
@pytest.mark.asyncio
async def test_execute_requires_authentication(client):
    response = await client.post(
        "/api/contacts/1/recommendations/1-follow_up/execute"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_execute_returns_404_for_unknown_contact(client):
    headers = await _register_and_login(client)
    response = await client.post(
        "/api/contacts/999999/recommendations/999999-follow_up/execute",
        headers=headers,
    )
    assert response.status_code == 404
    # Release 1.5 hardening (FIX 3): user-facing error text must be pt-BR,
    # never leak the backend's internal English message to the frontend.
    assert response.json()["detail"] == user_messages.CONTACT_NOT_FOUND


@pytest.mark.asyncio
async def test_execute_follow_up_creates_task_via_tool_registry(
    client, session_factory
):
    """The real end-to-end path: stale relationship -> follow_up
    recommendation -> confirmed -> create_task Tool actually runs -> a
    real Task row exists, linked to this contact -- and an audit log
    entry is recorded."""
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(
        session_factory,
        name="Relacionamento parado",
        last_interaction_at=datetime.now(timezone.utc) - timedelta(days=20),
    )

    workspace = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    recommendations = workspace.json()["recommendations"]
    follow_up = next(r for r in recommendations if r["type"] == "follow_up")
    assert follow_up["execution_target"] == "create_task"

    response = await client.post(
        f"/api/contacts/{contact.id}/recommendations/{follow_up['id']}/execute",
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "task_id" in body["result"]

    async with session_factory() as session:
        result = await session.execute(
            select(Task).where(Task.id == body["result"]["task_id"])
        )
        task = result.scalar_one()
        assert task.contact_id == contact.id
        assert task.user_id == owner.id
        assert "Relacionamento parado" in task.title

        log_result = await session.execute(
            select(LogEntry).where(
                LogEntry.source == "contacts:recommendation.follow_up"
            )
        )
        log_entry = log_result.scalars().first()
        assert log_entry is not None
        assert log_entry.payload["recommendation_id"] == follow_up["id"]
        assert log_entry.payload["supporting_signals"] == ["relationship_stale"]


@pytest.mark.asyncio
async def test_execute_manual_only_recommendation_returns_400(
    client, session_factory
):
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(session_factory, name="Tarefa atrasada")
    async with session_factory() as session:
        session.add(
            Task(
                user_id=owner.id,
                title="Atrasada",
                contact_id=contact.id,
                status=TaskStatus.PENDING,
                priority=TaskPriority.HIGH,
                due_date=datetime.now(timezone.utc) - timedelta(days=5),
            )
        )
        await session.commit()

    workspace = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    check_pending = next(
        r
        for r in workspace.json()["recommendations"]
        if r["type"] == "check_pending_tasks"
    )

    response = await client.post(
        f"/api/contacts/{contact.id}/recommendations/{check_pending['id']}/execute",
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == user_messages.RECOMMENDATION_NOT_EXECUTABLE


@pytest.mark.asyncio
async def test_execute_stale_recommendation_returns_404(client, session_factory):
    """Staleness guard: the recommendation was valid when computed, but
    the underlying signal no longer fires by the time execute is called
    (e.g. the task was completed in the meantime) -- must not blindly
    execute a stale action."""
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(session_factory, name="Ficou saudável")
    async with session_factory() as session:
        task = Task(
            user_id=owner.id,
            title="Atrasada",
            contact_id=contact.id,
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH,
            due_date=datetime.now(timezone.utc) - timedelta(days=5),
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)

    workspace = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    check_pending = next(
        r
        for r in workspace.json()["recommendations"]
        if r["type"] == "check_pending_tasks"
    )

    # The task gets completed before the recommendation is ever confirmed.
    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == task.id))
        stored_task = result.scalar_one()
        stored_task.status = TaskStatus.DONE
        await session.commit()

    response = await client.post(
        f"/api/contacts/{contact.id}/recommendations/{check_pending['id']}/execute",
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == user_messages.RECOMMENDATION_EXPIRED
