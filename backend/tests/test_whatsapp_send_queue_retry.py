"""Queue-level repetition of WhatsApp sends, through the REAL job worker.

Every test here runs jobs.worker.JobWorker.run_once() against the real
send_whatsapp_text handler and the real conversation_control tables (created
from the real alembic revisions). Only the transport is substituted, so each
provider call the worker causes is counted.
"""

import importlib.util
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

import jobs.handlers  # noqa: F401 -- registers the send handlers
from jobs.service import JobService
from jobs.worker import JobWorker
from models.job import JobStatus
from providers.whatsapp.base import WhatsAppProviderError
from services import conversation_control
from utils.config import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PHONE = "+5511999990000"


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
        _load("queue_mig_v1", BACKEND_ROOT / "alembic" / "versions" / "e610080001_pause_control.py"),
        _load("queue_mig_v2", BACKEND_ROOT / "alembic" / "versions" / "e610080002_review_delivery.py"),
    ]
    with Operations.context(MigrationContext.configure(sync_conn)):
        for migration in migrations:
            migration.upgrade()


class _Provider:
    """Stand-in transport: records every call, answers with a scripted outcome."""

    name = "evolution"
    default_instance = "store"

    def __init__(self, outcomes):
        self.calls: list[tuple] = []
        self._outcomes = list(outcomes)

    async def send_text(self, to, content, instance=None):
        self.calls.append((to, content, instance))
        outcome = self._outcomes.pop(0) if self._outcomes else {"key": {"id": "EVT-DEFAULT"}}
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _ambiguous_failure() -> WhatsAppProviderError:
    """What the real provider raises when a response never arrived: the request
    may or may not have been accepted."""
    error = WhatsAppProviderError("evolution request failed: ReadTimeout")
    error.__cause__ = httpx.ReadTimeout("simulated: response never arrived")
    return error


def _provably_unsent_failure() -> WhatsAppProviderError:
    """Connection refused before any byte left this process."""
    error = WhatsAppProviderError("evolution request failed: ConnectError")
    error.__cause__ = httpx.ConnectError("simulated: connection refused")
    return error


@pytest_asyncio.fixture
async def control_db(db_engine, monkeypatch):
    async with db_engine.begin() as conn:
        await conn.run_sync(_migrate_control_tables_sync)
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("jobs.worker.async_session_factory", sessions)
    monkeypatch.setattr(get_settings(), "jobs_retry_backoff_seconds", 0)
    return sessions


@pytest.fixture
def provider(monkeypatch):
    def install(outcomes):
        fake = _Provider(outcomes)
        monkeypatch.setattr("jobs.handlers.get_whatsapp_provider", lambda: fake)
        return fake

    return install


async def _enqueue_send(sessions, payload):
    async with sessions() as session:
        job = await JobService(session).enqueue("whatsapp.send_text", payload)
        return job.id


async def _run_worker_until_idle(rounds: int = 4) -> None:
    worker = JobWorker()
    for _ in range(rounds):
        await worker.run_once()


async def _job_status(sessions, job_id):
    from models.job import Job

    async with sessions() as session:
        return (await session.get(Job, job_id)).status


@pytest.mark.asyncio
async def test_an_unknown_outcome_send_is_never_resent_by_the_queue_retry(control_db, provider):
    """Reproduces the defect: the first attempt's outcome is unknown (the
    provider may have accepted it). The queue re-runs the job, and the
    handler must not call the transport again for that same job."""
    fake = provider([_ambiguous_failure(), {"key": {"id": "EVT-SHOULD-NOT-HAPPEN"}}])
    job_id = await _enqueue_send(control_db, {
        "to": PHONE, "content": "Temos o thinner 5L, R$ 45,00.", "instance": "store",
    })

    await _run_worker_until_idle()

    assert len(fake.calls) == 1, (
        f"o transporte foi chamado {len(fake.calls)} vezes para um unico job cujo "
        "resultado ficou desconhecido -- a fila repetiu o envio"
    )
    assert await _job_status(control_db, job_id) == JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_a_clean_send_is_sent_once_and_leaves_its_receipt(control_db, provider, monkeypatch):
    async def no_memory_work(*args, **kwargs):
        return False

    monkeypatch.setattr("services.messaging.contact_memory_service.record_interaction", no_memory_work)
    fake = provider([{"key": {"id": "EVT-CLEAN-1"}}])
    job_id = await _enqueue_send(control_db, {
        "to": PHONE, "content": "Pedido confirmado.", "instance": "store",
    })

    await _run_worker_until_idle()

    assert len(fake.calls) == 1
    assert await _job_status(control_db, job_id) == JobStatus.SUCCEEDED
    async with control_db() as session:
        row = await conversation_control._one(
            session,
            "SELECT COUNT(*) AS n FROM conversation_receipts WHERE instance=:inst AND external_id=:ext",
            {"inst": "store", "ext": "EVT-CLEAN-1"},
        )
    assert row["n"] == 1


@pytest.mark.asyncio
async def test_a_send_that_provably_never_left_is_retried_and_sent_once(control_db, provider, monkeypatch):
    async def no_memory_work(*args, **kwargs):
        return False

    monkeypatch.setattr("services.messaging.contact_memory_service.record_interaction", no_memory_work)
    fake = provider([_provably_unsent_failure(), {"key": {"id": "EVT-RETRY-OK"}}])
    job_id = await _enqueue_send(control_db, {
        "to": PHONE, "content": "Segue o endereco.", "instance": "store",
    })

    await _run_worker_until_idle()

    assert len(fake.calls) == 2, "uma falha comprovadamente anterior ao envio deveria permitir nova tentativa"
    assert await _job_status(control_db, job_id) == JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_a_paused_conversation_blocks_a_queued_plain_send(control_db, provider):
    """A human took over before this queued send ran: the transport must not
    be called, for Loja/B2B/Azusa exactly as for the Twin."""
    from models.contact import Contact

    async with control_db() as session:
        contact = Contact(name="Cliente Pausado", phone=PHONE.lstrip("+"))  # stored normalized, as inbound traffic is
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        await conversation_control.pause(session, contact.id, "store", event_id="human-takeover-1", reason="owner_replied")
        await session.commit()
    fake = provider([{"key": {"id": "EVT-SHOULD-NOT-HAPPEN"}}])
    await _enqueue_send(control_db, {"to": PHONE, "content": "Oi, sou o assistente.", "instance": "store"})

    await _run_worker_until_idle(rounds=1)

    assert fake.calls == []
