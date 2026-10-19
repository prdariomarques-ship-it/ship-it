"""WhatsApp -> DARIUS task flow, end to end through the REAL job worker and REAL handlers.

Mocked (external effects only): the DARIUS HTTP server (an in-process `httpx.MockTransport` that implements
the lifecycle contract the real runtime serves -- Idempotency-Key, statuses, result, cancel) and the Evolution
transport (a recording provider). Everything else -- webhook-side rows, guards, link table, job queue, send
handler with suspension/pause/output-safety gates -- is the real code.
"""
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import jobs.darius_whatsapp_jobs  # noqa: F401 -- registers submit/poll handlers
import jobs.handlers  # noqa: F401 -- registers inbound + send handlers
from auth.password import hash_password
from jobs.service import JobService
from jobs.worker import JobWorker
from models.contact import Contact
from models.darius_whatsapp_task import DariusWhatsAppTask
from models.job import Job, JobStatus
from models.log import LogEntry
from models.message import Message, MessageDirection, MessageMediaType
from models.user import User, UserRole
from providers.whatsapp.base import normalize_phone
from repositories.automation_suspension import AutomationSuspensionRepository
from services import conversation_control, darius_whatsapp
from services.darius_client import CircuitBreaker, DariusClient
from utils.config import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
INSTANCE = "store"
PHONE = "5511999990001"
TEXT = "Quero um orçamento de 3 latas de tinta branca fosca"
REPLY = "Olá! Posso sim: 3 latas de tinta branca fosca saem por R$ 297,00."


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
        _load("dw_mig_v1", BACKEND_ROOT / "alembic" / "versions" / "e610080001_pause_control.py"),
        _load("dw_mig_v2", BACKEND_ROOT / "alembic" / "versions" / "e610080002_review_delivery.py"),
    ]
    with Operations.context(MigrationContext.configure(sync_conn)):
        for migration in migrations:
            migration.upgrade()


class FakeDarius:
    """In-process stand-in for the DARIUS lifecycle contract (create / result / cancel)."""

    def __init__(self) -> None:
        self.tasks: dict[str, dict] = {}
        self.by_key: dict[str, str] = {}
        self.create_calls: list[dict] = []          # every POST /api/tasks seen (key + body)
        self.cancelled: list[str] = []
        self.fail_creates = 0                        # next N creates answer 503 WITHOUT applying
        self.apply_then_fail_creates = 0             # next N creates are applied, then answer 503
        self.reject_token = False                    # every request answers 401
        self.down = False                            # every request raises a connection error

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _summary(self, task: dict) -> dict:
        return {k: task[k] for k in ("id", "objective", "status", "createdAt", "updatedAt")}

    def set(self, task_id: str, status: str, result: str | None = None) -> None:
        self.tasks[task_id].update(status=status, result=result, updatedAt=self._now())

    def only_task_id(self) -> str:
        assert len(self.tasks) == 1, self.tasks
        return next(iter(self.tasks))

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("darius down")
        if self.reject_token:
            return httpx.Response(401, json={"error": "invalid token"})
        path = request.url.path
        if request.method == "POST" and path == "/api/tasks":
            key = request.headers.get("Idempotency-Key", "")
            body = json.loads(request.content)
            self.create_calls.append({"key": key, "body": body})
            if self.fail_creates > 0:
                self.fail_creates -= 1
                return httpx.Response(503, json={"error": "busy"})
            if key in self.by_key:
                return httpx.Response(200, json=self._summary(self.tasks[self.by_key[key]]))
            task_id = f"task-{len(self.tasks) + 1}"
            now = self._now()
            self.tasks[task_id] = {"id": task_id, "objective": body["objective"], "status": "PENDING",
                                   "createdAt": now, "updatedAt": now, "result": None}
            self.by_key[key] = task_id
            if self.apply_then_fail_creates > 0:
                self.apply_then_fail_creates -= 1
                return httpx.Response(503, json={"error": "applied but lost"})
            return httpx.Response(201, json=self._summary(self.tasks[task_id]))
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[:2] == ["api", "tasks"]:
            task = self.tasks.get(parts[2])
            if task is None:
                return httpx.Response(404, json={"error": "not found"})
            if request.method == "GET" and parts[3:] == ["result"]:
                done = task["status"] in ("COMPLETED", "FAILED", "CANCELLED")
                return httpx.Response(200, json={
                    "id": task["id"], "status": task["status"], "done": done,
                    "result": task["result"],  # a runtime may expose partial output on any done state
                    "error": "boom" if task["status"] == "FAILED" else None, "updatedAt": task["updatedAt"],
                })
            if request.method == "POST" and parts[3:] == ["cancel"]:
                self.cancelled.append(task["id"])
                self.set(task["id"], "CANCELLED")
                return httpx.Response(200, json={"id": task["id"], "status": "CANCELLED"})
        return httpx.Response(404, json={"error": "not found"})


class _Provider:
    name = "evolution"
    default_instance = INSTANCE

    def __init__(self):
        self.calls: list[tuple] = []

    async def send_text(self, to, content, instance=None):
        self.calls.append((to, content, instance))
        return {"key": {"id": f"EVT-{len(self.calls)}"}}


@pytest.fixture
def darius(monkeypatch):
    fake = FakeDarius()
    client = DariusClient(
        "http://darius.test", "service-token", transport=httpx.MockTransport(fake.handler),
        max_attempts=1, backoff=0.0, breaker=CircuitBreaker(1000, 1.0),
    )
    monkeypatch.setattr("services.darius_whatsapp.get_service_client", lambda: client)
    fake.client = client  # type: ignore[attr-defined]
    return fake


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    s = get_settings()
    for key, value in {
        "darius_whatsapp_enabled": True, "darius_whatsapp_instances": INSTANCE,
        "darius_whatsapp_poll_seconds": 0.0, "darius_whatsapp_reply_timeout_seconds": 900,
        "automation_suspended": False, "evolution_instance": INSTANCE, "evolution_personal_instance": "personal",
        "store_whatsapp_enabled": False, "auto_reply_max_message_age_seconds": 0,
        "jobs_retry_backoff_seconds": 0, "jobs_default_max_attempts": 3,
        "line_watch_instances": "", "evolution_media_extra_instances": "",
    }.items():
        monkeypatch.setattr(s, key, value)
    monkeypatch.setattr("services.darius_whatsapp.SUBMIT_BACKOFF_BASE_SECONDS", 0.0)


@pytest_asyncio.fixture
async def sessions(db_engine, monkeypatch):
    async with db_engine.begin() as conn:
        await conn.run_sync(_migrate_control_tables_sync)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("jobs.worker.async_session_factory", factory)
    async with factory() as db:
        db.add(User(email="owner@darioos.test", full_name="Owner", hashed_password=hash_password("supersecret1"),
                    role=UserRole.ADMIN, is_active=True))
        await db.commit()
    return factory


@pytest.fixture
def provider(monkeypatch):
    fake = _Provider()
    monkeypatch.setattr("jobs.handlers.get_whatsapp_provider", lambda: fake)

    async def no_memory_work(*args, **kwargs):
        return False

    monkeypatch.setattr("services.messaging.contact_memory_service.record_interaction", no_memory_work)
    return fake


_counter = {"n": 0}


async def _inbound(sessions, *, text: str = TEXT, instance: str = INSTANCE, external_id: str | None = None):
    _counter["n"] += 1
    async with sessions() as db:
        # stored normalised, as the webhook does: the send path resolves the contact by normalize_phone(to)
        contact = Contact(name="Cliente", phone=normalize_phone(f"55119999{_counter['n']:05d}"), preferences={})
        db.add(contact)
        await db.flush()
        message = Message(
            contact_id=contact.id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT,
            content=text, whatsapp_instance=instance, external_id=external_id or f"WAMID-{_counter['n']}",
        )
        db.add(message)
        await db.commit()
        return contact.id, message.id


async def _enqueue_inbound(sessions, contact_id, message_id, instance: str = INSTANCE) -> int:
    async with sessions() as db:
        job = await JobService(db).enqueue(
            "whatsapp.process_inbound", {"contact_id": contact_id, "message_id": message_id, "instance": instance}
        )
        return job.id


async def _drain(rounds: int = 25) -> None:
    worker = JobWorker()
    for _ in range(rounds):
        await worker.run_once()


async def _links(sessions) -> list[DariusWhatsAppTask]:
    async with sessions() as db:
        return list((await db.execute(select(DariusWhatsAppTask).order_by(DariusWhatsAppTask.id))).scalars())


async def _logs(sessions, source="darius_whatsapp") -> list[LogEntry]:
    async with sessions() as db:
        rows = await db.execute(select(LogEntry).where(LogEntry.source == source).order_by(LogEntry.id))
        return list(rows.scalars())


async def _jobs(sessions, name: str) -> list[Job]:
    async with sessions() as db:
        return list((await db.execute(select(Job).where(Job.name == name).order_by(Job.id))).scalars())


async def _contact_phone(sessions, contact_id) -> str:
    async with sessions() as db:
        return (await db.get(Contact, contact_id)).phone


# --- pure -------------------------------------------------------------------------
def test_dedupe_key_is_stable_and_scoped_by_instance():
    class M:
        id = 7
        external_id = "WAMID-1"

    a = darius_whatsapp.dedupe_key("store", M())
    assert a == darius_whatsapp.dedupe_key("store", M()) and a.startswith("wa-") and len(a) <= 64
    assert a != darius_whatsapp.dedupe_key("other", M())
    M.external_id = None  # type: ignore[assignment]
    assert darius_whatsapp.dedupe_key("store", M()) != a


def test_objective_has_no_phone_and_is_truncated():
    s = get_settings()
    text = darius_whatsapp.build_objective(s, INSTANCE, 42, "x" * 10_000)
    assert "#42" in text and "[mensagem truncada]" in text and len(text) < s.darius_whatsapp_max_objective_chars + 600
    assert PHONE not in text
    assert "DONE:" in text  # the DARIUS completion protocol is part of the objective


def test_routing_requires_flag_and_explicit_instance(monkeypatch):
    s = get_settings()
    assert darius_whatsapp.is_enabled_for(s, INSTANCE) and not darius_whatsapp.is_enabled_for(s, "other")
    assert not darius_whatsapp.is_enabled_for(s, "") and not darius_whatsapp.is_enabled_for(s, None)
    monkeypatch.setattr(s, "darius_whatsapp_enabled", False)
    assert not darius_whatsapp.is_enabled_for(s, INSTANCE)


# --- the happy path, with audit ----------------------------------------------------
@pytest.mark.asyncio
async def test_inbound_creates_a_task_and_only_a_completed_result_is_sent(sessions, provider, darius):
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    (link,) = await _links(sessions)
    assert link.status == "submitted" and link.darius_task_id == darius.only_task_id()
    assert provider.calls == []                                    # nothing is sent before DARIUS completes
    (call,) = darius.create_calls
    assert call["key"] == link.dedupe_key and TEXT in call["body"]["objective"]
    assert "5511999" not in call["body"]["objective"]               # no phone number leaves for the objective

    darius.set(link.darius_task_id, "COMPLETED", REPLY)
    await _drain()

    (link,) = await _links(sessions)
    assert link.status == "reply_queued" and link.reply_job_id is not None
    assert link.reply_chars == len(REPLY) and link.reply_sha256 == hashlib.sha256(REPLY.encode()).hexdigest()
    assert [(c[0], c[1]) for c in provider.calls] == [(await _contact_phone(sessions, cid), REPLY)]
    for job in await _jobs(sessions, "whatsapp.send_text"):
        assert job.status == JobStatus.SUCCEEDED

    logs = await _logs(sessions)
    assert [entry.payload["status"] for entry in logs][0] == "submitted"
    assert any("entregue à fila de envio" in entry.message for entry in logs)
    blob = " ".join(entry.message + json.dumps(entry.payload, default=str) for entry in logs)
    assert TEXT not in blob and REPLY not in blob                   # the audit trail holds no conversation content
    assert "5511999" not in blob


@pytest.mark.asyncio
async def test_a_duplicated_inbound_job_creates_one_task_and_one_reply(sessions, provider, darius):
    cid, mid = await _inbound(sessions)
    for _ in range(3):
        await _enqueue_inbound(sessions, cid, mid)

    await _drain()
    darius.set(darius.only_task_id(), "COMPLETED", REPLY)
    await _drain()

    # The worker may process the duplicates concurrently, so a losing job can legitimately re-send the create
    # while the winner is still in flight (SUBMITTING recovery). What must hold is that the shared
    # Idempotency-Key makes that harmless: ONE task in DARIUS, ONE link, ONE reply.
    links = await _links(sessions)
    assert len(links) == 1 and len(darius.tasks) == 1
    assert {call["key"] for call in darius.create_calls} == {links[0].dedupe_key}
    assert len(provider.calls) == 1
    # the duplicates are a normal outcome, not a crash: no inbound job failed or was retried
    inbound = await _jobs(sessions, "whatsapp.process_inbound")
    assert len(inbound) == 3 and all(j.status == JobStatus.SUCCEEDED and j.attempts == 1 for j in inbound)


async def test_losing_the_claim_race_does_not_expire_the_callers_session(sessions):
    """Regression: a rollback on the UNIQUE conflict used to expire the contact/message the job handler
    still holds, so the duplicate job crashed with MissingGreenlet and was retried."""
    from repositories.contact import ContactRepository
    from repositories.darius_whatsapp_task import DariusWhatsAppTaskRepository
    from repositories.message import MessageRepository

    cid, mid = await _inbound(sessions)
    async with sessions() as db:
        contact = await ContactRepository(db).get(cid)
        message = await MessageRepository(db).get(mid)
        repo = DariusWhatsAppTaskRepository(db)
        kwargs = dict(dedupe_key="wa-race", message_id=mid, contact_id=cid, instance=INSTANCE, control_revision=None)
        first, created_first = await repo.claim(**kwargs)
        second, created_second = await repo.claim(**kwargs)
        assert (created_first, created_second) == (True, False) and second.id == first.id
        # still usable without any lazy load (a lazy load here raises MissingGreenlet)
        assert contact.id == cid and message.id == mid and message.content


# --- authorization (DARIUS-side approval) ------------------------------------------
@pytest.mark.asyncio
async def test_nothing_is_sent_while_the_task_awaits_approval(sessions, provider, darius):
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)
    await _drain()
    task_id = darius.only_task_id()

    for status in ("PENDING", "PAUSED", "QUEUED", "RUNNING"):
        darius.set(task_id, status)
        await _drain(rounds=6)
        assert provider.calls == [] and (await _links(sessions))[0].status == "submitted"

    darius.set(task_id, "COMPLETED", REPLY)
    await _drain()
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_a_rejected_task_is_cancelled_and_nothing_is_sent(sessions, provider, darius):
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)
    await _drain()
    darius.set(darius.only_task_id(), "CANCELLED")

    await _drain()

    (link,) = await _links(sessions)
    assert link.status == "cancelled" and provider.calls == [] and link.finished_at is not None


@pytest.mark.asyncio
async def test_a_failed_task_is_recorded_as_failed_without_a_reply(sessions, provider, darius):
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)
    await _drain()
    darius.set(darius.only_task_id(), "FAILED")

    await _drain()

    (link,) = await _links(sessions)
    assert link.status == "failed" and link.last_error == "darius_task_failed" and provider.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["FAILED", "CANCELLED", "RUNNING", "PAUSED"])
async def test_partial_output_of_a_non_completed_task_is_never_sent(sessions, provider, darius, status):
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)
    await _drain()
    darius.set(darius.only_task_id(), status, "resposta parcial que nao pode sair")

    await _drain(rounds=8)

    assert provider.calls == []


@pytest.mark.asyncio
async def test_a_completed_task_with_an_empty_result_is_never_sent(sessions, provider, darius):
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)
    await _drain()
    darius.set(darius.only_task_id(), "COMPLETED", "   ")

    await _drain()

    (link,) = await _links(sessions)
    assert link.status == "failed" and link.last_error == "empty_result" and provider.calls == []


# --- failure handling ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_transient_create_failures_retry_with_the_same_key_and_create_one_task(sessions, provider, darius):
    darius.fail_creates = 2
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    (link,) = await _links(sessions)
    assert link.status == "submitted" and link.attempts == 3
    assert len(darius.tasks) == 1 and len({c["key"] for c in darius.create_calls}) == 1
    assert len(darius.create_calls) == 3


@pytest.mark.asyncio
async def test_a_create_whose_response_was_lost_does_not_duplicate_the_task(sessions, provider, darius):
    darius.apply_then_fail_creates = 1                 # DARIUS created the task, the 503 hid it
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    (link,) = await _links(sessions)
    assert link.status == "submitted" and len(darius.tasks) == 1 and link.darius_task_id == darius.only_task_id()


@pytest.mark.asyncio
async def test_exhausted_retries_end_failed_and_send_nothing(sessions, provider, darius):
    darius.down = True
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    (link,) = await _links(sessions)
    assert link.status == "failed" and link.last_error.endswith("attempts_exhausted")
    assert link.attempts == get_settings().jobs_default_max_attempts and provider.calls == []


@pytest.mark.asyncio
async def test_not_configured_is_skipped_with_no_fallback_to_the_local_pipeline(sessions, provider, monkeypatch):
    unconfigured = DariusClient("", "", max_attempts=1, backoff=0.0)
    monkeypatch.setattr("services.darius_whatsapp.get_service_client", lambda: unconfigured)

    async def must_not_run(*args, **kwargs):
        raise AssertionError("the local pipeline must not answer an instance routed to DARIUS")

    monkeypatch.setattr("orchestrator.pipeline.cognitive_pipeline.process", must_not_run)
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    (link,) = await _links(sessions)
    assert link.status == "skipped" and link.last_error == "darius_not_configured" and provider.calls == []
    assert (await _jobs(sessions, "whatsapp.process_inbound"))[0].status == JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_a_rejected_credential_fails_without_retrying(sessions, provider, darius):
    darius.reject_token = True
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    (link,) = await _links(sessions)
    assert link.status == "failed" and link.last_error.startswith("DariusAuthError")
    assert link.attempts == 1 and len(darius.create_calls) == 0 and provider.calls == []


@pytest.mark.asyncio
async def test_no_result_in_the_window_expires_cancels_and_never_sends_late(sessions, provider, darius, monkeypatch):
    monkeypatch.setattr(get_settings(), "darius_whatsapp_reply_timeout_seconds", 0)
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    (link,) = await _links(sessions)
    assert link.status == "expired" and darius.cancelled == [link.darius_task_id]
    darius.set(link.darius_task_id, "COMPLETED", REPLY)            # a late result, after the window
    await _drain()
    assert provider.calls == [] and (await _links(sessions))[0].status == "expired"


@pytest.mark.asyncio
async def test_darius_unreachable_while_polling_keeps_waiting_then_expires(sessions, provider, darius, monkeypatch):
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)
    await _drain(rounds=6)
    assert (await _links(sessions))[0].status == "submitted"

    darius.down = True
    await _drain(rounds=6)
    assert (await _links(sessions))[0].status == "submitted"       # an outage is not a verdict on the task

    monkeypatch.setattr(get_settings(), "darius_whatsapp_reply_timeout_seconds", 0)
    await _drain(rounds=6)
    link = (await _links(sessions))[0]
    assert link.status == "expired" and link.last_error == "reply_window_elapsed_darius_unreachable"
    assert provider.calls == []


# --- the guards that already protect the local flows still apply ----------------------
@pytest.mark.asyncio
async def test_a_global_suspension_creates_no_task(sessions, provider, darius):
    async with sessions() as db:
        await AutomationSuspensionRepository(db).suspend("global", "teste", None)
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    assert darius.tasks == {} and await _links(sessions) == [] and provider.calls == []


@pytest.mark.asyncio
async def test_a_suspension_after_submission_withholds_the_ready_reply(sessions, provider, darius):
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)
    await _drain()
    async with sessions() as db:
        await AutomationSuspensionRepository(db).suspend("instance:store", "teste", None)
    darius.set(darius.only_task_id(), "COMPLETED", REPLY)

    await _drain()

    assert provider.calls == []                                     # withheld at the transport gate
    (link,) = await _links(sessions)
    assert link.status == "reply_queued"
    assert (await _jobs(sessions, "whatsapp.send_text"))[0].status == JobStatus.SUCCEEDED
    assert any("retido" in e.message for e in await _logs(sessions, "automation_suspension"))


@pytest.mark.asyncio
async def test_a_human_pause_after_submission_blocks_the_reply(sessions, provider, darius):
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)
    await _drain()
    async with sessions() as db:
        await conversation_control.pause(db, cid, INSTANCE, "evt-human-1", "owner took over")
        await db.commit()
    darius.set(darius.only_task_id(), "COMPLETED", REPLY)

    await _drain()

    assert provider.calls == []


@pytest.mark.asyncio
async def test_pause_and_resume_after_submission_still_blocks_the_stale_reply(sessions, provider, darius):
    """The conversation is active again at send time, but a human took over in between: the reply was
    generated against an older conversation state and must not be released."""
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)
    await _drain()
    async with sessions() as db:
        owner_id = (await db.execute(select(User.id))).scalar_one()
        paused = await conversation_control.pause(db, cid, INSTANCE, "evt-human-3", "owner took over")
        await db.commit()
        await conversation_control.resume(db, cid, INSTANCE, paused["revision"], owner_id)
        await db.commit()
    darius.set(darius.only_task_id(), "COMPLETED", REPLY)

    await _drain()

    assert provider.calls == []
    assert (await _links(sessions))[0].control_revision == 0


@pytest.mark.asyncio
async def test_a_conversation_already_paused_creates_no_task(sessions, provider, darius):
    cid, mid = await _inbound(sessions)
    async with sessions() as db:
        await conversation_control.pause(db, cid, INSTANCE, "evt-human-2", "owner took over")
        await db.commit()
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    assert darius.tasks == {} and await _links(sessions) == []


@pytest.mark.asyncio
async def test_the_loop_guard_runs_before_a_task_is_created(sessions, provider, darius, monkeypatch):
    async def suppressed(*args, **kwargs):
        return True

    monkeypatch.setattr("jobs.handlers._loop_guard_or_alert", suppressed)
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    assert darius.tasks == {} and await _links(sessions) == []


@pytest.mark.asyncio
async def test_opt_out_is_honoured_before_any_task(sessions, provider, darius, monkeypatch):
    monkeypatch.setattr(get_settings(), "store_whatsapp_enabled", True)
    cid, mid = await _inbound(sessions, text="PARAR")
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    assert darius.tasks == {} and await _links(sessions) == []
    assert len(provider.calls) == 1                                # the opt-out acknowledgement
    async with sessions() as db:
        assert (await db.get(Contact, cid)).preferences["store_contact_opt_out"] is True


@pytest.mark.asyncio
async def test_non_text_messages_are_not_routed(sessions, provider, darius):
    cid, mid = await _inbound(sessions)
    async with sessions() as db:
        message = await db.get(Message, mid)
        message.media_type = MessageMediaType.AUDIO
        await db.commit()
    await _enqueue_inbound(sessions, cid, mid)

    await _drain()

    assert darius.tasks == {} and await _links(sessions) == []


@pytest.mark.asyncio
async def test_an_instance_not_listed_keeps_using_the_legacy_pipeline(sessions, provider, darius, monkeypatch):
    class _Result:
        reply = "resposta do pipeline local"

    seen: list[str] = []

    async def legacy(*, db, user, message, contact_id, **kw):
        seen.append(message)
        return _Result()

    monkeypatch.setattr("orchestrator.pipeline.cognitive_pipeline.process", legacy)
    cid, mid = await _inbound(sessions, instance="elsewhere")
    await _enqueue_inbound(sessions, cid, mid, instance="elsewhere")

    await _drain()

    assert seen == [TEXT] and darius.tasks == {} and await _links(sessions) == []
    assert [c[1] for c in provider.calls] == ["resposta do pipeline local"]


# --- migration ---------------------------------------------------------------------------
def test_migration_creates_the_link_table_and_downgrade_refuses_with_rows():
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration = _load("dw_mig_v3", BACKEND_ROOT / "alembic" / "versions" / "e7a42c9f1b35_darius_whatsapp_tasks.py")
    assert migration.down_revision == "d91b5e7a3c20"
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE messages (id INTEGER PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE contacts (id INTEGER PRIMARY KEY)"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert "darius_whatsapp_tasks" in sa.inspect(conn).get_table_names()
        conn.execute(sa.text("INSERT INTO messages (id) VALUES (1)"))
        conn.execute(sa.text("INSERT INTO contacts (id) VALUES (1)"))
        conn.execute(sa.text(
            "INSERT INTO darius_whatsapp_tasks (dedupe_key, message_id, contact_id, instance, status, history, "
            "created_at, updated_at) VALUES "
            "('k', 1, 1, 'store', 'submitted', '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        with Operations.context(MigrationContext.configure(conn)):
            with pytest.raises(RuntimeError):
                migration.downgrade()
        conn.execute(sa.text("DELETE FROM darius_whatsapp_tasks"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert "darius_whatsapp_tasks" not in sa.inspect(conn).get_table_names()
