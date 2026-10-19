"""Automation suspension (global / per instance): enforced at the real send path.

The send tests run the REAL job worker against the REAL `send_whatsapp_text`
handler and the real conversation-control tables; only the transport is a
recording fake, so "nothing was sent" means the transport was never called.
"""
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
from models.job import Job, JobStatus
from models.log import LogEntry
from models.user import User, UserRole
from repositories.app_setting import AppSettingRepository
from services import app_settings, automation_suspension as suspension
from utils.config import get_settings

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
def _restore_suspension_settings():
    settings = get_settings()
    before = (settings.automation_suspended, settings.automation_suspended_instances)
    yield
    settings.automation_suspended, settings.automation_suspended_instances = before


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


async def _status(sessions, job_id):
    async with sessions() as session:
        return (await session.get(Job, job_id)).status


async def _logs(sessions, source):
    async with sessions() as session:
        return list((await session.execute(select(LogEntry).where(LogEntry.source == source))).scalars())


# --- pure functions ------------------------------------------------------------
def test_parse_instances_sorts_dedups_and_drops_invalid_tokens():
    assert suspension.parse_instances(" store, personal,store,,bad name,-x, b2b-sales ") == [
        "b2b-sales", "personal", "store",
    ]
    assert suspension.parse_instances(None) == [] and suspension.parse_instances("") == []


def test_suspension_reason_global_instance_and_none():
    s = get_settings()
    s.automation_suspended, s.automation_suspended_instances = False, ""
    assert suspension.suspension_reason(s, "store") is None
    s.automation_suspended_instances = "store"
    assert suspension.suspension_reason(s, "store") == "instance:store"
    assert suspension.suspension_reason(s, "personal") is None
    assert suspension.suspension_reason(s, "") is None and suspension.suspension_reason(s, None) is None
    s.automation_suspended = True
    assert suspension.suspension_reason(s, "personal") == "global"
    assert suspension.suspension_reason(s, None) == "global"


def test_only_owner_alerts_are_protected():
    assert suspension.is_protected_from_suspension({"owner_alert": True})
    assert suspension.is_protected_from_suspension({"_twin_alert_dedup_key": "k"})
    assert not suspension.is_protected_from_suspension({"to": PHONE, "content": "x"})
    assert not suspension.is_protected_from_suspension({"is_autopilot_reply": True})


# --- enforcement at the transport chokepoint -------------------------------------
@pytest.mark.asyncio
async def test_global_suspension_withholds_a_message_queued_before_it(sessions, provider):
    job_id = await _enqueue(sessions, {"to": PHONE, "content": "Resposta pronta.", "instance": "store"})
    get_settings().automation_suspended = True  # suspended AFTER queuing, BEFORE the worker runs

    await _run_worker()

    assert provider.calls == []
    assert await _status(sessions, job_id) == JobStatus.SUCCEEDED  # completes: never retried/released later
    logs = await _logs(sessions, "automation_suspension")
    assert len(logs) == 1 and logs[0].payload["scope"] == "global"
    assert "Resposta pronta" not in logs[0].message and "Resposta pronta" not in str(logs[0].payload)


@pytest.mark.asyncio
async def test_instance_suspension_only_affects_that_instance(sessions, provider):
    get_settings().automation_suspended_instances = "store"
    await _enqueue(sessions, {"to": PHONE, "content": "da loja", "instance": "store"})
    await _enqueue(sessions, {"to": OWNER, "content": "do pessoal", "instance": "personal"})

    await _run_worker()

    # (the fake is not an EvolutionProvider, so the handler does not pass `instance` through to it)
    assert [c[1] for c in provider.calls] == ["do pessoal"]


@pytest.mark.asyncio
async def test_a_send_without_instance_resolves_the_provider_default_instance(sessions, provider):
    get_settings().automation_suspended_instances = "store"  # provider.default_instance == "store"
    await _enqueue(sessions, {"to": PHONE, "content": "sem instancia explicita"})

    await _run_worker()

    assert provider.calls == []


@pytest.mark.asyncio
async def test_owner_alerts_still_go_out_during_a_global_suspension(sessions, provider):
    get_settings().automation_suspended = True
    await _enqueue(
        sessions, {"to": OWNER, "content": "[Linha] fora do ar", "instance": "personal", "owner_alert": True}
    )
    await _enqueue(sessions, {"to": PHONE, "content": "automatica", "instance": "store"})

    await _run_worker()

    assert [c[1] for c in provider.calls] == ["[Linha] fora do ar"]


@pytest.mark.asyncio
async def test_a_withheld_autopilot_reply_leaves_no_reservation_behind(sessions, provider, db_engine):
    get_settings().automation_suspended = True
    await _enqueue(sessions, {
        "to": PHONE, "content": "resposta do gemeo", "instance": "store", "is_autopilot_reply": True,
        "_twin_contact_id": 1, "_twin_revision": 0, "_twin_source_message_id": 7,
    })

    await _run_worker()

    assert provider.calls == []
    async with db_engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM conversation_send_intents"))).scalar() == 0


@pytest.mark.asyncio
async def test_lifting_the_suspension_sends_new_messages_but_not_the_withheld_ones(sessions, provider):
    settings = get_settings()
    settings.automation_suspended = True
    await _enqueue(sessions, {"to": PHONE, "content": "retida", "instance": "store"})
    await _run_worker()
    assert provider.calls == []

    settings.automation_suspended = False
    await _enqueue(sessions, {"to": PHONE, "content": "nova", "instance": "store"})
    await _run_worker()

    assert [c[1] for c in provider.calls] == ["nova"]


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
async def test_suspension_routes_require_admin(client, users, method, path):
    body = {"suspended": True, "reason": "teste de acesso"}
    anon = await client.request(method, API + path, json=body if method == "PUT" else None)
    assert anon.status_code == 401
    plain = await client.request(method, API + path, json=body if method == "PUT" else None,
                                 headers=_headers(users[UserRole.USER]))
    assert plain.status_code == 403
    assert get_settings().automation_suspended is False


@pytest.mark.asyncio
async def test_admin_suspends_globally_with_reason_and_audit(client, users, db_engine):
    admin = users[UserRole.ADMIN]
    response = await client.put(
        API + "/suspension/global", headers=_headers(admin),
        json={"suspended": True, "reason": "loop com outra automação"},
    )
    assert response.status_code == 200
    assert response.json() == {"global_suspended": True, "suspended_instances": []}
    assert get_settings().automation_suspended is True

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        logs = list((await session.execute(
            select(LogEntry).where(LogEntry.source == "automation_suspension"))).scalars())
        assert len(logs) == 1 and logs[0].level == "warning"
        assert logs[0].payload["actor_id"] == admin.id and logs[0].payload["reason"] == "loop com outra automação"
        row = await AppSettingRepository(session).get_by_key("automation_suspended")
        assert row is not None and row.value == "true" and row.updated_by == admin.id

    state = await client.get(API + "/suspension", headers=_headers(admin))
    assert state.json()["global_suspended"] is True


@pytest.mark.asyncio
async def test_admin_manages_instances_incrementally(client, users):
    h = _headers(users[UserRole.ADMIN])
    body = {"suspended": True, "reason": "linha com loop"}
    assert (await client.put(API + "/suspension/instances/store", headers=h, json=body)).json()[
        "suspended_instances"] == ["store"]
    assert (await client.put(API + "/suspension/instances/personal", headers=h, json=body)).json()[
        "suspended_instances"] == ["personal", "store"]
    resumed = await client.put(API + "/suspension/instances/store", headers=h,
                               json={"suspended": False, "reason": "loop resolvido"})
    assert resumed.json() == {"global_suspended": False, "suspended_instances": ["personal"]}


@pytest.mark.asyncio
async def test_suspension_changes_are_validated(client, users):
    h = _headers(users[UserRole.ADMIN])
    assert (await client.put(API + "/suspension/global", headers=h, json={"suspended": True})).status_code == 422
    assert (await client.put(API + "/suspension/global", headers=h,
                             json={"suspended": True, "reason": "  "})).status_code == 422
    assert (await client.put(API + "/suspension/global", headers=h,
                             json={"suspended": True, "reason": "x" * 501})).status_code == 422
    bad = await client.put(API + "/suspension/instances/bad name!", headers=h,
                           json={"suspended": True, "reason": "motivo valido"})
    assert bad.status_code == 422
    assert get_settings().automation_suspended is False and get_settings().automation_suspended_instances == ""


@pytest.mark.asyncio
async def test_suspension_survives_a_restart(client, users, db_engine):
    await client.put(API + "/suspension/global", headers=_headers(users[UserRole.ADMIN]),
                     json={"suspended": True, "reason": "teste de persistencia"})
    settings = get_settings()
    settings.automation_suspended = False  # what a fresh process starts with (.env default)

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        await app_settings.apply_persisted_overrides(session)

    assert settings.automation_suspended is True


@pytest.mark.asyncio
async def test_suspension_entries_appear_in_the_settings_catalog(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        keys = {item["key"]: item for item in await app_settings.list_settings(session)}
    assert keys["automation_suspended"]["editable"] and keys["automation_suspended_instances"]["editable"]
