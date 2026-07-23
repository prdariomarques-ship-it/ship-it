"""GET /contacts/priority -- Release 1.5, P0-3: cross-contact ranking.

Contacts ranked by `priority_score` descending, computed via 2 aggregate
queries (never one per contact) -- see contacts/intelligence.py and
CONTACT_INTELLIGENCE_ARCHITECTURE.md #12/#13. Signal/tier/score
correctness is unit-tested in test_contact_intelligence.py; the
assertions here are only about ordering, `limit`, isolation and the
route not being swallowed by contacts_router's generic `/{item_id}`.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.contact import Contact
from models.task import Task, TaskPriority, TaskStatus
from models.user import User


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _register_and_login(client) -> dict[str, str]:
    await client.post(
        "/api/auth/register",
        json={
            "email": "priority@example.com",
            "full_name": "Owner",
            "password": "supersecret1",
        },
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "priority@example.com", "password": "supersecret1"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _owner_user(session_factory) -> User:
    from sqlalchemy import select

    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == "priority@example.com")
        )
        return result.scalar_one()


async def _new_contact(session_factory, **kwargs) -> Contact:
    async with session_factory() as session:
        contact = Contact(**kwargs)
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


@pytest.mark.asyncio
async def test_priority_requires_authentication(client):
    response = await client.get("/api/contacts/priority")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_route_is_not_swallowed_by_the_generic_item_id_catch_all(
    client, session_factory
):
    """Regression guard: contacts_router's generic GET /{item_id} must
    never intercept /contacts/priority (see main.py's router-ordering
    comment). If it did, this would 422 (failing to parse "priority" as an
    int id) instead of returning a list."""
    headers = await _register_and_login(client)
    response = await client.get("/api/contacts/priority", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_empty_address_book_returns_an_empty_list(client, session_factory):
    headers = await _register_and_login(client)
    response = await client.get("/api/contacts/priority", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_contacts_are_ranked_by_priority_score_descending(
    client, session_factory
):
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    now = datetime.now(timezone.utc)

    await _new_contact(
        session_factory, name="Saudável", last_interaction_at=now - timedelta(hours=1)
    )
    at_risk = await _new_contact(
        session_factory, name="Em risco", last_interaction_at=now - timedelta(days=90)
    )
    async with session_factory() as session:
        session.add(
            Task(
                user_id=owner.id,
                title="Atrasada",
                contact_id=at_risk.id,
                status=TaskStatus.PENDING,
                priority=TaskPriority.HIGH,
                due_date=now - timedelta(days=5),
            )
        )
        await session.commit()

    response = await client.get("/api/contacts/priority", headers=headers)
    assert response.status_code == 200
    body = response.json()
    names = [item["name"] for item in body]
    assert names.index("Em risco") < names.index("Saudável")

    at_risk_item = next(item for item in body if item["name"] == "Em risco")
    assert at_risk_item["relationship_status"]["tier"] == "at_risk"
    assert "overdue_commitment" in {
        s["code"] for s in at_risk_item["relationship_status"]["signals"]
    }
    # Release 1.5 hardening (FIX 6): this contact has TWO urgent-severity
    # signals (overdue_commitment AND relationship_at_risk) -- exactly the
    # tie the frontend's removed severity-only sort could get wrong.
    # `primary_reason` must reflect the backend's own fixed code-priority
    # order (contacts/intelligence.py::primary_risk_signal /
    # _ACTION_PRIORITY), which ranks overdue_commitment first.
    assert at_risk_item["primary_reason"] is not None
    assert "pending task" in at_risk_item["primary_reason"]


@pytest.mark.asyncio
async def test_limit_is_honored(client, session_factory):
    headers = await _register_and_login(client)
    now = datetime.now(timezone.utc)
    for i in range(5):
        await _new_contact(
            session_factory,
            name=f"Contato {i}",
            last_interaction_at=now - timedelta(days=i),
        )

    response = await client.get(
        "/api/contacts/priority", params={"limit": 2}, headers=headers
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_a_contact_with_no_signals_still_appears_in_the_ranking(
    client, session_factory
):
    """Never silently drop a contact just because nothing fired for it."""
    headers = await _register_and_login(client)
    await _new_contact(
        session_factory,
        name="Sem sinais",
        last_interaction_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    response = await client.get("/api/contacts/priority", headers=headers)
    body = response.json()
    assert any(item["name"] == "Sem sinais" for item in body)
    no_signals_item = next(item for item in body if item["name"] == "Sem sinais")
    # No risk signal fired -- primary_reason must be null, not an empty
    # string or a fabricated placeholder.
    assert no_signals_item["primary_reason"] is None
    entry = next(item for item in body if item["name"] == "Sem sinais")
    assert entry["relationship_status"]["tier"] == "healthy"


@pytest.mark.asyncio
async def test_overdue_task_isolation_between_users(client, session_factory):
    """A different user's overdue task must never inflate this user's
    contact's priority score -- Task stays owner-scoped exactly as
    everywhere else (see test_contact_workspace.py's own isolation test)."""
    headers = await _register_and_login(client)
    now = datetime.now(timezone.utc)
    shared_contact = await _new_contact(
        session_factory, name="Contato compartilhado", last_interaction_at=now
    )

    async with session_factory() as session:
        from auth.password import hash_password

        other_user = User(
            email="other-priority@example.com",
            full_name="Other",
            hashed_password=hash_password("supersecret1"),
        )
        session.add(other_user)
        await session.commit()
        await session.refresh(other_user)
        session.add(
            Task(
                user_id=other_user.id,
                title="Tarefa de outro usuário",
                contact_id=shared_contact.id,
                status=TaskStatus.PENDING,
                priority=TaskPriority.HIGH,
                due_date=now - timedelta(days=5),
            )
        )
        await session.commit()

    response = await client.get("/api/contacts/priority", headers=headers)
    body = response.json()
    entry = next(item for item in body if item["name"] == "Contato compartilhado")
    assert "overdue_commitment" not in {
        s["code"] for s in entry["relationship_status"]["signals"]
    }
