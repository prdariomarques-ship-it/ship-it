"""GoalManager: persistent goals, dependencies, recurrence, approval
workflow, progress tracking, scoring and the EventBus/MemoryManager/agent-tool
integrations. Mirrors the style of tests/test_jobs.py and
tests/test_memory_manager.py.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from agents.tools.base import ToolContext
from agents.tools.goals import (
    complete_goal_tool,
    create_goal_tool,
    list_goals_tool,
    update_goal_progress_tool,
)
from events.bus import event_bus
from goals.scoring import priority_score
from goals.service import ApprovalRequiredError, CyclicDependencyError, GoalService
from models.goal import Goal, GoalPriority, GoalStatus
from models.log import LogEntry
from models.user import User
from repositories.goal import GoalRepository


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def user(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="goals@example.com", full_name="Dario", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


# --- Service: creation, status, approval gate --------------------------------
@pytest.mark.asyncio
async def test_create_goal_defaults_to_pending(session_factory, user):
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(user.id, "Aprender violão")
    assert goal.status == GoalStatus.PENDING
    assert goal.requires_approval is False
    assert goal.progress_percent == 0


@pytest.mark.asyncio
async def test_create_goal_requiring_approval_starts_awaiting_approval(
    session_factory, user
):
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(
            user.id, "Enviar proposta ao cliente", requires_approval=True
        )
    assert goal.status == GoalStatus.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_status_update_on_awaiting_approval_goal_is_rejected(
    session_factory, user
):
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(
            user.id, "X", requires_approval=True
        )
    async with session_factory() as session:
        with pytest.raises(ApprovalRequiredError):
            await GoalService(session).update_status(goal, GoalStatus.IN_PROGRESS)


@pytest.mark.asyncio
async def test_awaiting_approval_goal_can_still_be_cancelled_directly(
    session_factory, user
):
    """Cancelling (rejecting) doesn't need elevated trust the way progressing does."""
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(
            user.id, "X", requires_approval=True
        )
    async with session_factory() as session:
        fresh = await GoalRepository(session).get(goal.id)
        updated = await GoalService(session).update_status(fresh, GoalStatus.CANCELLED)
    assert updated.status == GoalStatus.CANCELLED


@pytest.mark.asyncio
async def test_approve_goal_moves_it_to_pending_and_records_approver(
    session_factory, user
):
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(
            user.id, "X", requires_approval=True
        )
    async with session_factory() as session:
        fresh = await GoalRepository(session).get(goal.id)
        approved = await GoalService(session).approve_goal(
            fresh, approved_by_id=user.id
        )
    assert approved.status == GoalStatus.PENDING
    assert approved.approved_by_id == user.id
    assert approved.approved_at is not None


@pytest.mark.asyncio
async def test_approving_a_goal_not_awaiting_approval_raises(session_factory, user):
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(user.id, "X")  # already PENDING
    async with session_factory() as session:
        with pytest.raises(ApprovalRequiredError):
            await GoalService(session).approve_goal(goal, approved_by_id=user.id)


# --- Dependencies / cycle detection -------------------------------------------
@pytest.mark.asyncio
async def test_goal_is_blocked_while_dependency_incomplete(session_factory, user):
    async with session_factory() as session:
        service = GoalService(session)
        base = await service.create_goal(user.id, "Base")
        dependent = await service.create_goal(user.id, "Dependente")
        await service.add_dependency(dependent.id, base.id)

    async with session_factory() as session:
        assert await GoalService(session).is_ready(dependent.id) is False


@pytest.mark.asyncio
async def test_goal_becomes_ready_once_dependency_completes(session_factory, user):
    async with session_factory() as session:
        service = GoalService(session)
        base = await service.create_goal(user.id, "Base")
        dependent = await service.create_goal(user.id, "Dependente")
        await service.add_dependency(dependent.id, base.id)

    async with session_factory() as session:
        base_fresh = await GoalRepository(session).get(base.id)
        await GoalService(session).update_status(base_fresh, GoalStatus.COMPLETED)

    async with session_factory() as session:
        assert await GoalService(session).is_ready(dependent.id) is True


@pytest.mark.asyncio
async def test_self_dependency_is_rejected(session_factory, user):
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(user.id, "X")
    async with session_factory() as session:
        with pytest.raises(CyclicDependencyError):
            await GoalService(session).add_dependency(goal.id, goal.id)


@pytest.mark.asyncio
async def test_transitive_cycle_is_rejected(session_factory, user):
    async with session_factory() as session:
        service = GoalService(session)
        a = await service.create_goal(user.id, "A")
        b = await service.create_goal(user.id, "B")
        c = await service.create_goal(user.id, "C")
        await service.add_dependency(b.id, a.id)  # b depends on a
        await service.add_dependency(c.id, b.id)  # c depends on b

    async with session_factory() as session:
        # a depends on c would close the loop a -> c -> b -> a
        with pytest.raises(CyclicDependencyError):
            await GoalService(session).add_dependency(a.id, c.id)


@pytest.mark.asyncio
async def test_ready_goals_excludes_blocked_and_awaiting_approval(
    session_factory, user
):
    async with session_factory() as session:
        service = GoalService(session)
        base = await service.create_goal(user.id, "Base")
        blocked = await service.create_goal(user.id, "Blocked")
        await service.add_dependency(blocked.id, base.id)
        await service.create_goal(user.id, "Needs approval", requires_approval=True)
        ready_one = await service.create_goal(user.id, "Ready")

    async with session_factory() as session:
        ready = await GoalService(session).ready_goals(user.id)
    ready_ids = {g.id for g in ready}
    assert ready_ids == {base.id, ready_one.id}


# --- Recurrence ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_completing_a_recurring_goal_spawns_the_next_occurrence(
    session_factory, user
):
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(
            user.id, "Revisão semanal", recurrence_interval_days=7
        )

    async with session_factory() as session:
        fresh = await GoalRepository(session).get(goal.id)
        completed = await GoalService(session).update_status(
            fresh, GoalStatus.COMPLETED
        )

    async with session_factory() as session:
        occurrences = await GoalRepository(session).recurrence_occurrences(completed.id)
    assert len(occurrences) == 1
    next_goal = occurrences[0]
    assert next_goal.status == GoalStatus.PENDING
    assert next_goal.recurrence_parent_id == completed.id
    assert next_goal.recurrence_interval_days == 7


@pytest.mark.asyncio
async def test_recurrence_chain_always_points_at_the_original_goal(
    session_factory, user
):
    async with session_factory() as session:
        service = GoalService(session)
        first = await service.create_goal(user.id, "Diária", recurrence_interval_days=1)

    async with session_factory() as session:
        first_fresh = await GoalRepository(session).get(first.id)
        completed_first = await GoalService(session).update_status(
            first_fresh, GoalStatus.COMPLETED
        )

    async with session_factory() as session:
        occurrences = await GoalRepository(session).recurrence_occurrences(first.id)
    second = occurrences[0]

    async with session_factory() as session:
        second_fresh = await GoalRepository(session).get(second.id)
        await GoalService(session).update_status(second_fresh, GoalStatus.COMPLETED)

    async with session_factory() as session:
        all_occurrences = await GoalRepository(session).recurrence_occurrences(first.id)
    # second's own spawn must chain back to `first`, not to `second`.
    assert len(all_occurrences) == 2
    assert {g.recurrence_parent_id for g in all_occurrences} == {first.id}
    assert (
        completed_first.id == first.id
    )  # sanity: completing doesn't reset the row's own id


@pytest.mark.asyncio
async def test_completing_a_non_recurring_goal_does_not_spawn_anything(
    session_factory, user
):
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(user.id, "Only once")
    async with session_factory() as session:
        fresh = await GoalRepository(session).get(goal.id)
        completed = await GoalService(session).update_status(
            fresh, GoalStatus.COMPLETED
        )
    async with session_factory() as session:
        assert await GoalRepository(session).recurrence_occurrences(completed.id) == []


# --- Progress tracking -----------------------------------------------------------
@pytest.mark.asyncio
async def test_update_progress_clamps_to_0_100(session_factory, user):
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(user.id, "X")

    async with session_factory() as session:
        fresh = await GoalRepository(session).get(goal.id)
        over = await GoalService(session).update_progress(fresh, 150)
    assert over.progress_percent == 100

    async with session_factory() as session:
        over_fresh = await GoalRepository(session).get(over.id)
        under = await GoalService(session).update_progress(over_fresh, -10)
    assert under.progress_percent == 0


# --- Resume after restart (state survives; stale IN_PROGRESS is discoverable) ---
@pytest.mark.asyncio
async def test_goal_state_survives_a_fresh_session(session_factory, user):
    """A fresh session/repository instance (standing in for a process
    restart) sees exactly the state a prior session committed."""
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(user.id, "Persistente")
        await GoalService(session).update_progress(goal, 42)

    async with session_factory() as session:
        reloaded = await GoalRepository(session).get(goal.id)
    assert reloaded.progress_percent == 42


@pytest.mark.asyncio
async def test_stuck_in_progress_finds_stale_goals_only(session_factory, user):
    async with session_factory() as session:
        service = GoalService(session)
        stale = await service.create_goal(user.id, "Stale")
        fresh = await service.create_goal(user.id, "Fresh")
        pending = await service.create_goal(user.id, "Still pending")

    async with session_factory() as session:
        repository = GoalRepository(session)
        stale_fresh = await repository.get(stale.id)
        await repository.update(stale_fresh, status=GoalStatus.IN_PROGRESS)
        fresh_fresh = await repository.get(fresh.id)
        await repository.update(fresh_fresh, status=GoalStatus.IN_PROGRESS)

    threshold = datetime.now(timezone.utc) + timedelta(hours=1)
    async with session_factory() as session:
        stuck = await GoalRepository(session).stuck_in_progress(threshold)
    stuck_ids = {g.id for g in stuck}
    assert stale.id in stuck_ids
    assert (
        fresh.id in stuck_ids
    )  # both updated "now", both older than a future threshold
    assert pending.id not in stuck_ids  # never left PENDING, not IN_PROGRESS


# --- Priority scoring ------------------------------------------------------------
def _goal(priority: GoalPriority, deadline: datetime | None) -> Goal:
    return Goal(priority=priority, deadline=deadline)


def test_higher_priority_scores_higher_with_no_deadline():
    low = priority_score(_goal(GoalPriority.LOW, None))
    urgent = priority_score(_goal(GoalPriority.URGENT, None))
    assert urgent > low


def test_no_deadline_gets_no_bonus():
    now = datetime.now(timezone.utc)
    no_deadline = priority_score(_goal(GoalPriority.MEDIUM, None), now=now)
    far_deadline = priority_score(
        _goal(GoalPriority.MEDIUM, now + timedelta(days=100)), now=now
    )
    assert no_deadline == far_deadline  # 100 days out is effectively "no bonus" too


def test_closer_deadline_scores_higher():
    now = datetime.now(timezone.utc)
    soon = priority_score(_goal(GoalPriority.MEDIUM, now + timedelta(days=1)), now=now)
    later = priority_score(
        _goal(GoalPriority.MEDIUM, now + timedelta(days=10)), now=now
    )
    assert soon > later


def test_overdue_deadline_is_capped_not_unbounded():
    now = datetime.now(timezone.utc)
    barely_overdue = priority_score(
        _goal(GoalPriority.MEDIUM, now - timedelta(days=1)), now=now
    )
    very_overdue = priority_score(
        _goal(GoalPriority.MEDIUM, now - timedelta(days=365)), now=now
    )
    assert barely_overdue == very_overdue  # both clamped at the max bonus


@pytest.mark.asyncio
async def test_ready_goals_ranks_by_score_not_creation_order(session_factory, user):
    async with session_factory() as session:
        service = GoalService(session)
        await service.create_goal(user.id, "Low", priority=GoalPriority.LOW)
        await service.create_goal(user.id, "Urgent", priority=GoalPriority.URGENT)
        await service.create_goal(user.id, "Medium", priority=GoalPriority.MEDIUM)

    async with session_factory() as session:
        ready = await GoalService(session).ready_goals(user.id)
    assert [g.title for g in ready] == ["Urgent", "Medium", "Low"]


# --- EventBus + audit log integration --------------------------------------------
@pytest.mark.asyncio
async def test_create_goal_publishes_to_event_bus_and_records_audit_log(
    session_factory, user
):
    received = []

    async def handler(event):
        received.append(event)

    event_bus.subscribe("goal.created", handler)
    try:
        async with session_factory() as session:
            goal = await GoalService(session).create_goal(user.id, "Observed")
    finally:
        event_bus.unsubscribe_all()

    assert len(received) == 1
    assert received[0].payload["goal_id"] == goal.id
    assert received[0].payload["title"] == "Observed"

    async with session_factory() as session:
        from sqlalchemy import select

        logs = (
            (
                await session.execute(
                    select(LogEntry).where(LogEntry.source == f"goal:{goal.id}")
                )
            )
            .scalars()
            .all()
        )
    assert any("created" in entry.message for entry in logs)


# --- MemoryManager integration (best-effort) --------------------------------------
@pytest.mark.asyncio
async def test_completing_a_goal_records_a_memory(session_factory, user):
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(user.id, "Aprender espanhol")

    with patch(
        "memory.manager.memory_manager.remember", new=AsyncMock(return_value=1)
    ) as mocked:
        async with session_factory() as session:
            fresh = await GoalRepository(session).get(goal.id)
            await GoalService(session).update_status(fresh, GoalStatus.COMPLETED)
    mocked.assert_awaited_once()
    assert "Aprender espanhol" in mocked.call_args.kwargs["content"]


@pytest.mark.asyncio
async def test_completing_a_goal_survives_memory_manager_failure(session_factory, user):
    """Qdrant/memory being unavailable must never block a goal from completing."""
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(user.id, "X")

    with patch(
        "memory.manager.memory_manager.remember",
        new=AsyncMock(side_effect=RuntimeError("qdrant down")),
    ):
        async with session_factory() as session:
            fresh = await GoalRepository(session).get(goal.id)
            completed = await GoalService(session).update_status(
                fresh, GoalStatus.COMPLETED
            )
    assert completed.status == GoalStatus.COMPLETED


# --- Agent tools (Planner integration) --------------------------------------------
@pytest.mark.asyncio
async def test_create_goal_tool(session_factory, user):
    async with session_factory() as session:
        context = ToolContext(db=session, user=user)
        result = await create_goal_tool.run(
            context, {"title": "Ferramenta", "priority": "high"}
        )
    assert '"ok": true' in result.lower()
    assert "Ferramenta" in result


@pytest.mark.asyncio
async def test_list_goals_tool_filters_by_status(session_factory, user):
    async with session_factory() as session:
        await GoalService(session).create_goal(user.id, "A")
    async with session_factory() as session:
        b = await GoalService(session).create_goal(user.id, "B")
        await GoalService(session).update_status(b, GoalStatus.CANCELLED)

    async with session_factory() as session:
        context = ToolContext(db=session, user=user)
        result = await list_goals_tool.run(context, {"status": "cancelled"})
    assert "B" in result
    assert '"A"' not in result


@pytest.mark.asyncio
async def test_update_goal_progress_tool(session_factory, user):
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(user.id, "X")

    async with session_factory() as session:
        context = ToolContext(db=session, user=user)
        result = await update_goal_progress_tool.run(
            context, {"goal_id": goal.id, "progress_percent": 60}
        )
    assert "60" in result


@pytest.mark.asyncio
async def test_complete_goal_tool_on_awaiting_approval_goal_reports_error_without_raising(
    session_factory, user
):
    """The tool must never let the model bypass the human-approval gate."""
    async with session_factory() as session:
        goal = await GoalService(session).create_goal(
            user.id, "X", requires_approval=True
        )

    async with session_factory() as session:
        context = ToolContext(db=session, user=user)
        result = await complete_goal_tool.run(context, {"goal_id": goal.id})
    assert "error" in result.lower()

    async with session_factory() as session:
        untouched = await GoalRepository(session).get(goal.id)
    assert untouched.status == GoalStatus.AWAITING_APPROVAL


# --- HTTP API: CRUD, approval, dependencies, isolation ----------------------------
@pytest.fixture
async def other_auth_headers(client) -> dict[str, str]:
    await client.post(
        "/api/auth/register",
        json={
            "email": "other@example.com",
            "full_name": "Other",
            "password": "supersecret1",
        },
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "other@example.com", "password": "supersecret1"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_api_create_and_get_goal(client, auth_headers):
    created = await client.post(
        "/api/goals",
        json={"title": "API goal", "priority": "high"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"

    fetched = await client.get(f"/api/goals/{body['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "API goal"


@pytest.mark.asyncio
async def test_api_cross_user_isolation_returns_404(
    client, auth_headers, other_auth_headers
):
    created = await client.post(
        "/api/goals", json={"title": "Mine"}, headers=auth_headers
    )
    goal_id = created.json()["id"]

    response = await client.get(f"/api/goals/{goal_id}", headers=other_auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_approve_requires_admin(client, auth_headers, other_auth_headers):
    """`auth_headers` is the first-ever user in a fresh DB, so it's ADMIN by
    construction; `other_auth_headers` registers second, so it's a plain USER."""
    created = await client.post(
        "/api/goals",
        json={"title": "Needs approval", "requires_approval": True},
        headers=auth_headers,
    )
    goal_id = created.json()["id"]

    forbidden = await client.post(
        f"/api/goals/{goal_id}/approve", headers=other_auth_headers
    )
    assert forbidden.status_code == 403

    approved = await client.post(f"/api/goals/{goal_id}/approve", headers=auth_headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_api_status_update_blocked_while_awaiting_approval(client, auth_headers):
    created = await client.post(
        "/api/goals",
        json={"title": "X", "requires_approval": True},
        headers=auth_headers,
    )
    goal_id = created.json()["id"]

    response = await client.patch(
        f"/api/goals/{goal_id}/status",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_api_dependency_cycle_returns_409(client, auth_headers):
    a = (
        await client.post("/api/goals", json={"title": "A"}, headers=auth_headers)
    ).json()
    b = (
        await client.post("/api/goals", json={"title": "B"}, headers=auth_headers)
    ).json()

    ok = await client.post(
        f"/api/goals/{b['id']}/dependencies",
        json={"depends_on_id": a["id"]},
        headers=auth_headers,
    )
    assert ok.status_code == 201

    cycle = await client.post(
        f"/api/goals/{a['id']}/dependencies",
        json={"depends_on_id": b["id"]},
        headers=auth_headers,
    )
    assert cycle.status_code == 409


@pytest.mark.asyncio
async def test_api_remove_nonexistent_dependency_returns_404(client, auth_headers):
    a = (
        await client.post("/api/goals", json={"title": "A"}, headers=auth_headers)
    ).json()
    b = (
        await client.post("/api/goals", json={"title": "B"}, headers=auth_headers)
    ).json()

    response = await client.delete(
        f"/api/goals/{a['id']}/dependencies/{b['id']}", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_progress_out_of_range_is_rejected_at_the_schema_level(
    client, auth_headers
):
    created = await client.post("/api/goals", json={"title": "X"}, headers=auth_headers)
    goal_id = created.json()["id"]

    response = await client.patch(
        f"/api/goals/{goal_id}/progress",
        json={"progress_percent": 150},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_api_ready_endpoint_excludes_awaiting_approval(client, auth_headers):
    await client.post("/api/goals", json={"title": "Ready"}, headers=auth_headers)
    await client.post(
        "/api/goals",
        json={"title": "Needs approval", "requires_approval": True},
        headers=auth_headers,
    )

    response = await client.get("/api/goals/ready", headers=auth_headers)
    titles = {g["title"] for g in response.json()}
    assert titles == {"Ready"}


@pytest.mark.asyncio
async def test_api_history_reflects_recorded_transitions(client, auth_headers):
    created = await client.post("/api/goals", json={"title": "X"}, headers=auth_headers)
    goal_id = created.json()["id"]
    await client.patch(
        f"/api/goals/{goal_id}/progress",
        json={"progress_percent": 50},
        headers=auth_headers,
    )

    history = await client.get(f"/api/goals/{goal_id}/history", headers=auth_headers)
    assert history.status_code == 200
    messages = [entry["message"] for entry in history.json()]
    assert any("created" in m for m in messages)
    assert any("progress_updated" in m for m in messages)


@pytest.mark.asyncio
async def test_api_history_is_owner_scoped(client, auth_headers, other_auth_headers):
    created = await client.post(
        "/api/goals", json={"title": "Mine"}, headers=auth_headers
    )
    goal_id = created.json()["id"]

    response = await client.get(
        f"/api/goals/{goal_id}/history", headers=other_auth_headers
    )
    assert response.status_code == 404
