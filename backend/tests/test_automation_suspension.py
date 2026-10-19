"""Automation suspension (global / per instance): atomic persistence + enforcement at the real send path.

The send tests run the REAL job worker against the REAL `send_whatsapp_text`
handler and the real conversation-control tables; only the transport is a
recording fake, so "nothing was sent" means the transport was never called.
State lives in the `automation_suspensions` table (one row per scope).
"""
import asyncio
import importlib.util
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

import jobs.handlers  # noqa: F401 -- registers the send handler
from auth.jwt import create_access_token
from auth.password import hash_password
from jobs.service import JobService
from jobs.worker import JobWorker
from models.automation_suspension import AutomationSuspension
from models.job import Job, JobStatus
from models.log import LogEntry
from models.user import User, UserRole
from repositories.automation_suspension import AutomationSuspensionRepository
from services import automation_suspension as suspension
from utils.config import Settings, get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PHONE = "+5511999990000"
OWNER = "+5511988887777"
API = "/api/admin/automation"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migrate_control_tables_sync(sync_conn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migrations = [
        _load("susp_mig_v1", BACKEND_ROOT / "alembic" / "versions" / "e610080001_pause_control.py"),
        _load("susp_mig_v2", BACKEND_ROOT / "alembic" / "versions" / "e610080002_review_delivery.py"),
    ]
    with Operations.context(MigrationContext.configure(sync_conn)):
        for migration in migrations:
            migration.upgrade()


class _Provider:
    name = "evolution"
    default_instance = "store"

    def __init__(self):
        self.calls: list[tuple] = []

    async def send_text(self, to, content, instance=None):
        self.calls.append((to, content, instance))
        return {"key": {"id": f"EVT-{len(self.calls)}"}}


@pytest.fixture(autouse=True)
def _configured_instances(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "automation_suspended", False)
    monkeypatch.setattr(settings, "evolution_instance", "store")
    monkeypatch.setattr(settings, "evolution_personal_instance", "personal")
    monkeypatch.setattr(settings, "line_watch_instances", "")
    monkeypatch.setattr(settings, "evolution_media_extra_instances", "")


@pytest_asyncio.fixture
async def sessions(db_engine, monkeypatch):
    async with db_engine.begin() as conn:
        await conn.run_sync(_migrate_control_tables_sync)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("jobs.worker.async_session_factory", factory)
    monkeypatch.setattr(get_settings(), "jobs_retry_backoff_seconds", 0)
    return factory


@pytest.fixture
def provider(monkeypatch):
    fake = _Provider()
    monkeypatch.setattr("jobs.handlers.get_whatsapp_provider", lambda: fake)

    async def no_memory_work(*args, **kwargs):
        return False

    monkeypatch.setattr("services.messaging.contact_memory_service.record_interaction", no_memory_work)
    return fake


async def _enqueue(sessions, payload) -> int:
    async with sessions() as session:
        return (await JobService(session).enqueue("whatsapp.send_text", payload)).id


async def _run_worker(rounds: int = 3) -> None:
    worker = JobWorker()
    for _ in range(rounds):
        await worker.run_once()


async def _job(sessions, job_id) -> Job:
    async with sessions() as session:
        return await session.get(Job, job_id)


async def _logs(sessions, source):
    async with sessions() as session:
        return list((await session.execute(select(LogEntry).where(LogEntry.source == source))).scalars())


async def _suspend(sessions, scope: str, reason: str = "motivo de teste") -> bool:
    async with sessions() as session:
        return await AutomationSuspensionRepository(session).suspend(scope, reason, None)


async def _resume(sessions, scope: str) -> bool:
    async with sessions() as session:
        return await AutomationSuspensionRepository(session).resume(scope)


async def _scopes(sessions) -> list[str]:
    async with sessions() as session:
        return [r.scope for r in await AutomationSuspensionRepository(session).list_all()]


# --- pure functions ------------------------------------------------------------
def test_configured_instances_is_the_union_of_every_configured_source(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "line_watch_instances", "watch1, store")
    monkeypatch.setattr(settings, "evolution_media_extra_instances", "extra1")
    assert suspension.configured_instances(settings) == [
        "azusa-church", "b2b-sales", "extra1", "personal", "store", "watch1",
    ]


def test_canonical_instance_matches_case_insensitively_and_rejects_the_rest():
    settings = get_settings()
    assert suspension.canonical_instance(settings, "STORE") == "store"
    with pytest.raises(suspension.UnknownInstance):
        suspension.canonical_instance(settings, "ghost")
    for bad in ("", "bad name", "-x", "a" * 65, "x/y"):
        with pytest.raises(suspension.InvalidSuspensionRequest):
            suspension.canonical_instance(settings, bad)


def test_only_owner_alerts_are_protected():
    assert suspension.is_protected_from_suspension({"owner_alert": True})
    assert suspension.is_protected_from_suspension({"_twin_alert_dedup_key": "k"})
    assert not suspension.is_protected_from_suspension({"to": PHONE, "content": "x"})
    assert not suspension.is_protected_from_suspension({"is_autopilot_reply": True})


@pytest.mark.asyncio
async def test_suspension_reason_global_instance_environment_and_none(sessions):
    s = get_settings()
    async with sessions() as db:
        assert await suspension.suspension_reason(db, s, "store") is None
    await _suspend(sessions, "instance:store")
    async with sessions() as db:
        assert await suspension.suspension_reason(db, s, "store") == "instance:store"
        assert await suspension.suspension_reason(db, s, "personal") is None
        assert await suspension.suspension_reason(db, s, "") is None
        assert await suspension.suspension_reason(db, s, None) is None
    await _suspend(sessions, "global")
    async with sessions() as db:
        assert await suspension.suspension_reason(db, s, "personal") == "global"
        assert await suspension.suspension_reason(db, s, None) == "global"
    await _resume(sessions, "global")
    await _resume(sessions, "instance:store")
    s.automation_suspended = True  # static env kill switch, no database row
    async with sessions() as db:
        assert await suspension.suspension_reason(db, s, "personal") == "global"


# --- atomic persistence ---------------------------------------------------------
@pytest.mark.asyncio
async def test_repository_suspend_is_idempotent_and_resume_reports_whether_it_removed(sessions):
    assert await _suspend(sessions, "instance:store", "primeiro") is True
    assert await _suspend(sessions, "instance:store", "segundo") is False
    async with sessions() as db:
        row = await AutomationSuspensionRepository(db).get_by_scope("instance:store")
        assert row is not None and row.reason == "segundo"
    assert await _scopes(sessions) == ["instance:store"]
    assert await _resume(sessions, "instance:store") is True
    assert await _resume(sessions, "instance:store") is False
    assert await _scopes(sessions) == []


@pytest.mark.asyncio
async def test_losing_the_insert_race_and_a_concurrent_delete_still_converges(sessions, monkeypatch):
    """The INSERT is the arbiter; if the row vanishes between the failed INSERT and the lookup, retry once."""
    await _suspend(sessions, "instance:store", "inicial")
    original = AutomationSuspensionRepository.get_by_scope
    calls = {"n": 0}

    async def vanish_once(self, scope):
        calls["n"] += 1
        if calls["n"] == 1:
            await self.session.execute(
                AutomationSuspension.__table__.delete().where(AutomationSuspension.scope == scope))
            await self.session.commit()
            return None
        return await original(self, scope)

    monkeypatch.setattr(AutomationSuspensionRepository, "get_by_scope", vanish_once)
    assert await _suspend(sessions, "instance:store", "reinserido") is True
    monkeypatch.undo()
    assert await _scopes(sessions) == ["instance:store"]


@pytest.mark.asyncio
async def test_concurrent_edits_of_different_instances_never_overwrite_each_other(sessions):
    names = [f"inst{i}" for i in range(8)]
    results = await asyncio.gather(*[_suspend(sessions, f"instance:{n}") for n in names])
    assert all(results)
    assert await _scopes(sessions) == sorted(f"instance:{n}" for n in names)
    # resume half of them concurrently with suspending the others
    await asyncio.gather(
        *[_resume(sessions, f"instance:{n}") for n in names[:4]],
        *[_suspend(sessions, f"instance:{n}", "outra") for n in names[4:]],
    )
    assert await _scopes(sessions) == sorted(f"instance:{n}" for n in names[4:])


@pytest.mark.asyncio
async def test_concurrent_identical_suspensions_leave_exactly_one_row(sessions):
    outcomes = await asyncio.gather(*[_suspend(sessions, "global", f"motivo {i}") for i in range(6)])
    assert outcomes.count(True) == 1
    assert await _scopes(sessions) == ["global"]


@pytest.mark.asyncio
async def test_state_is_read_from_the_database_not_from_process_memory(sessions):
    """A restart (fresh Settings, fresh sessions) sees the suspension: nothing lives in memory."""
    await _suspend(sessions, "global", "persistente")
    await _suspend(sessions, "instance:store", "persistente")
    fresh_settings = Settings()  # what a newly started process begins with
    fresh_factory = async_sessionmaker(sessions.kw["bind"], expire_on_commit=False)
    async with fresh_factory() as db:
        assert await suspension.suspension_reason(db, fresh_settings, "personal") == "global"
        snapshot = await suspension.state(db, fresh_settings)
    assert snapshot["global_suspended"] is True and snapshot["suspended_instances"] == ["store"]


# --- enforcement at the transport chokepoint -------------------------------------
@pytest.mark.asyncio
async def test_global_suspension_withholds_a_message_queued_before_it(sessions, provider):
    job_id = await _enqueue(sessions, {"to": PHONE, "content": "Resposta pronta.", "instance": "store"})
    await _suspend(sessions, "global")  # suspended AFTER queuing, BEFORE the worker runs

    await _run_worker()

    assert provider.calls == []
    job = await _job(sessions, job_id)
    assert job.status == JobStatus.SUCCEEDED and job.attempts == 1  # completes: never retried/released later
    logs = await _logs(sessions, "automation_suspension")
    assert len(logs) == 1 and logs[0].payload["scope"] == "global"
    assert "Resposta pronta" not in logs[0].message and "Resposta pronta" not in str(logs[0].payload)


@pytest.mark.asyncio
async def test_instance_suspension_only_affects_that_instance(sessions, provider):
    await _suspend(sessions, "instance:store")
    await _enqueue(sessions, {"to": PHONE, "content": "da loja", "instance": "store"})
    await _enqueue(sessions, {"to": OWNER, "content": "do pessoal", "instance": "personal"})

    await _run_worker()

    # (the fake is not an EvolutionProvider, so the handler does not pass `instance` through to it)
    assert [c[1] for c in provider.calls] == ["do pessoal"]


@pytest.mark.asyncio
async def test_a_send_without_instance_resolves_the_provider_default_instance(sessions, provider):
    await _suspend(sessions, "instance:store")  # provider.default_instance == "store"
    await _enqueue(sessions, {"to": PHONE, "content": "sem instancia explicita"})

    await _run_worker()

    assert provider.calls == []


@pytest.mark.asyncio
async def test_owner_alerts_still_go_out_during_a_global_suspension(sessions, provider):
    await _suspend(sessions, "global")
    await _enqueue(
        sessions, {"to": OWNER, "content": "[Linha] fora do ar", "instance": "personal", "owner_alert": True}
    )
    await _enqueue(
        sessions, {"to": OWNER, "content": "[Loop] suspenso", "instance": "store", "_twin_alert_dedup_key": "k1"}
    )
    await _enqueue(sessions, {"to": PHONE, "content": "automatica", "instance": "store"})

    await _run_worker()

    assert sorted(c[1] for c in provider.calls) == ["[Linha] fora do ar", "[Loop] suspenso"]


@pytest.mark.asyncio
async def test_a_withheld_autopilot_reply_leaves_no_reservation_behind(sessions, provider, db_engine):
    await _suspend(sessions, "global")
    await _enqueue(sessions, {
        "to": PHONE, "content": "resposta do gemeo", "instance": "store", "is_autopilot_reply": True,
        "_twin_contact_id": 1, "_twin_revision": 0, "_twin_source_message_id": 7,
    })

    await _run_worker()

    assert provider.calls == []
    async with db_engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM conversation_send_intents"))).scalar() == 0


@pytest.mark.asyncio
async def test_resuming_never_replays_withheld_messages_in_a_burst(sessions, provider):
    await _suspend(sessions, "instance:store")
    withheld = [
        await _enqueue(sessions, {"to": PHONE, "content": f"retida {i}", "instance": "store"})
        for i in range(5)
    ]
    await _run_worker(rounds=6)
    assert provider.calls == []
    for job_id in withheld:
        assert (await _job(sessions, job_id)).status == JobStatus.SUCCEEDED

    assert await _resume(sessions, "instance:store") is True
    await _run_worker(rounds=6)  # many worker passes after the resume: still nothing is replayed
    assert provider.calls == []
    for job_id in withheld:
        assert (await _job(sessions, job_id)).attempts == 1  # never retried either

    await _enqueue(sessions, {"to": PHONE, "content": "nova", "instance": "store"})
    await _run_worker()
    assert [c[1] for c in provider.calls] == ["nova"]


@pytest.mark.asyncio
async def test_a_message_still_pending_at_resume_time_is_sent_once(sessions, provider):
    """Only messages the worker actually withheld are lost; a job not yet processed when the
    suspension ends was never blocked, so it goes out exactly once."""
    await _suspend(sessions, "global")
    await _enqueue(sessions, {"to": PHONE, "content": "ainda na fila", "instance": "store"})
    await _resume(sessions, "global")

    await _run_worker(rounds=4)

    assert [c[1] for c in provider.calls] == ["ainda na fila"]


# --- admin API -------------------------------------------------------------------
@pytest_asyncio.fixture
async def users(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    out = {}
    async with factory() as session:
        for email, role in (("admin@darioos.test", UserRole.ADMIN), ("user@darioos.test", UserRole.USER)):
            user = User(email=email, full_name=email, hashed_password=hash_password("supersecret1"),
                        role=role, is_active=True)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            out[role] = user
    return out


def _headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [
    ("GET", "/suspension"), ("PUT", "/suspension/global"), ("PUT", "/suspension/instances/store"),
])
async def test_suspension_routes_require_admin(client, users, db_engine, method, path):
    body = {"suspended": True, "reason": "teste de acesso"}
    anon = await client.request(method, API + path, json=body if method == "PUT" else None)
    assert anon.status_code == 401
    plain = await client.request(method, API + path, json=body if method == "PUT" else None,
                                 headers=_headers(users[UserRole.USER]))
    assert plain.status_code == 403
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    assert await _scopes(factory) == []


@pytest.mark.asyncio
async def test_admin_suspends_globally_with_reason_and_audit(client, users, db_engine):
    admin = users[UserRole.ADMIN]
    response = await client.put(
        API + "/suspension/global", headers=_headers(admin),
        json={"suspended": True, "reason": "loop com outra automação"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["global_suspended"] is True and body["changed"] is True
    assert body["global_forced_by_environment"] is False and body["suspended_instances"] == []
    assert "store" in body["configured_instances"]
    assert body["details"][0]["scope"] == "global" and body["details"][0]["actor_id"] == admin.id

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        logs = list((await session.execute(
            select(LogEntry).where(LogEntry.source == "automation_suspension"))).scalars())
        assert len(logs) == 1 and logs[0].level == "warning"
        assert logs[0].payload["actor_id"] == admin.id and logs[0].payload["reason"] == "loop com outra automação"
        row = await AutomationSuspensionRepository(session).get_by_scope("global")
        assert row is not None and row.actor_id == admin.id

    state = await client.get(API + "/suspension", headers=_headers(admin))
    assert state.json()["global_suspended"] is True and state.json()["changed"] is None


@pytest.mark.asyncio
async def test_admin_manages_instances_incrementally_and_canonicalises_the_name(client, users):
    h = _headers(users[UserRole.ADMIN])
    body = {"suspended": True, "reason": "linha com loop"}
    first = await client.put(API + "/suspension/instances/STORE", headers=h, json=body)
    assert first.status_code == 200 and first.json()["suspended_instances"] == ["store"]
    second = await client.put(API + "/suspension/instances/personal", headers=h, json=body)
    assert second.json()["suspended_instances"] == ["personal", "store"]
    resumed = await client.put(API + "/suspension/instances/store", headers=h,
                               json={"suspended": False, "reason": "loop resolvido"})
    assert resumed.json()["suspended_instances"] == ["personal"] and resumed.json()["global_suspended"] is False


@pytest.mark.asyncio
async def test_repeated_edits_are_idempotent_and_report_changed_false(client, users):
    h = _headers(users[UserRole.ADMIN])
    body = {"suspended": True, "reason": "motivo valido"}
    assert (await client.put(API + "/suspension/global", headers=h, json=body)).json()["changed"] is True
    assert (await client.put(API + "/suspension/global", headers=h, json=body)).json()["changed"] is False
    off = {"suspended": False, "reason": "retomada"}
    assert (await client.put(API + "/suspension/global", headers=h, json=off)).json()["changed"] is True
    again = await client.put(API + "/suspension/global", headers=h, json=off)
    assert again.status_code == 200 and again.json()["changed"] is False


@pytest.mark.asyncio
async def test_suspending_an_unconfigured_instance_is_404_and_persists_nothing(client, users, db_engine):
    h = _headers(users[UserRole.ADMIN])
    response = await client.put(API + "/suspension/instances/ghost", headers=h,
                                json={"suspended": True, "reason": "typo no nome"})
    assert response.status_code == 404
    assert "não configurada" in response.json()["detail"]  # our 404, not a missing route
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    assert await _scopes(factory) == []


@pytest.mark.asyncio
async def test_resuming_an_unconfigured_instance_cleans_a_stale_row(client, users, db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _suspend(factory, "instance:retired")
    h = _headers(users[UserRole.ADMIN])
    response = await client.put(API + "/suspension/instances/retired", headers=h,
                                json={"suspended": False, "reason": "instancia desativada"})
    assert response.status_code == 200, response.text
    assert response.json()["changed"] is True
    assert await _scopes(factory) == []


@pytest.mark.asyncio
async def test_suspension_changes_are_validated(client, users, db_engine):
    h = _headers(users[UserRole.ADMIN])
    assert (await client.put(API + "/suspension/global", headers=h, json={"suspended": True})).status_code == 422
    assert (await client.put(API + "/suspension/global", headers=h,
                             json={"suspended": True, "reason": "  "})).status_code == 422
    assert (await client.put(API + "/suspension/global", headers=h,
                             json={"suspended": True, "reason": "x" * 501})).status_code == 422
    for bad in ("bad name!", "-x"):
        r = await client.put(API + f"/suspension/instances/{bad}", headers=h,
                             json={"suspended": True, "reason": "motivo valido"})
        assert r.status_code == 422, bad
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    assert await _scopes(factory) == []


@pytest.mark.asyncio
async def test_environment_kill_switch_is_reported_and_not_cleared_by_resume(client, users):
    h = _headers(users[UserRole.ADMIN])
    get_settings().automation_suspended = True
    state = await client.get(API + "/suspension", headers=h)
    assert state.json()["global_suspended"] is True and state.json()["global_forced_by_environment"] is True
    resumed = await client.put(API + "/suspension/global", headers=h,
                               json={"suspended": False, "reason": "tentativa de retomar"})
    assert resumed.json()["global_suspended"] is True  # still forced by AUTOMATION_SUSPENDED


# --- migration -------------------------------------------------------------------
def test_migration_creates_the_table_and_downgrade_refuses_while_suspensions_are_active():
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration = _load("susp_mig_v3", BACKEND_ROOT / "alembic" / "versions" / "d91b5e7a3c20_automation_suspensions.py")
    assert migration.down_revision == "c8f3a1d27b40"
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert "automation_suspensions" in sa.inspect(conn).get_table_names()
        conn.execute(sa.text(
            "INSERT INTO automation_suspensions (scope, reason, created_at, updated_at) "
            "VALUES ('global', 'x', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        with Operations.context(MigrationContext.configure(conn)):
            with pytest.raises(RuntimeError):
                migration.downgrade()
        conn.execute(sa.text("DELETE FROM automation_suspensions"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert "automation_suspensions" not in sa.inspect(conn).get_table_names()


@pytest.mark.asyncio
async def test_suspension_since_is_timezone_aware_even_when_the_driver_drops_tzinfo(client, users):
    from datetime import datetime

    h = _headers(users[UserRole.ADMIN])
    body = {"suspended": True, "reason": "motivo valido"}
    await client.put(API + "/suspension/instances/store", headers=h, json=body)
    details = (await client.get(API + "/suspension", headers=h)).json()["details"]
    assert details and all(d["since"] for d in details)
    for d in details:
        assert datetime.fromisoformat(d["since"]).utcoffset() is not None