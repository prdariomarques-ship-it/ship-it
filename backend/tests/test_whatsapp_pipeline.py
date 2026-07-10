"""Integration tests for the Phase 4.1 end-to-end WhatsApp flow:

    webhook -> persist -> event -> job queue -> AI Orchestrator
            -> agent (memory + tools) -> reply job -> send -> persist + memory

Every step is exercised for real (no mocking the orchestrator or the agent),
except the outbound provider HTTP call itself, which would otherwise try to
reach a real WhatsApp gateway.
"""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from jobs.registry import _HANDLERS
from jobs.worker import JobWorker
from models.contact import Contact
from models.job import Job, JobStatus
from models.message import Message, MessageDirection
from repositories.user import UserRepository


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _isolated_handlers():
    """One test in this file overwrites the whatsapp.process_inbound handler
    to force a failure; restore the real one afterward for every other test."""
    saved = dict(_HANDLERS)
    yield
    _HANDLERS.clear()
    _HANDLERS.update(saved)


@pytest.fixture
def worker(session_factory, monkeypatch):
    monkeypatch.setattr("jobs.worker.async_session_factory", session_factory)
    monkeypatch.setattr("jobs.handlers.async_session_factory", session_factory)
    return JobWorker()


def _send_text_mock():
    return patch(
        "providers.whatsapp.openwa.provider.OpenWAProvider.send_text",
        new=AsyncMock(return_value={"status": "ok"}),
    )


async def _jobs_named(session_factory, name: str) -> list[Job]:
    async with session_factory() as session:
        jobs = (await session.execute(select(Job).where(Job.name == name))).scalars().all()
        return list(jobs)


@pytest.mark.asyncio
async def test_full_pipeline_webhook_to_reply(client, auth_headers, session_factory, worker):
    """The whole objective of Fase 4.1: a message arrives and the contact gets
    an automatic reply, with every step's side effects verifiable."""
    response = await client.post(
        "/api/webhooks/whatsapp",
        json={
            "from": "5511977778888@c.us",
            "body": "Bom dia, preciso de ajuda",
            "notifyName": "Cliente E2E",
            "id": "wamid-e2e-1",
            "type": "text",
        },
    )
    assert response.status_code == 200
    ack = response.json()
    assert ack["status"] == "received"

    # 1) Persisted, 2) contact created, 3) auto-reply job enqueued.
    contacts = await client.get("/api/contacts", headers=auth_headers)
    assert contacts.json()[0]["phone"] == "5511977778888"

    messages = await client.get("/api/messages", headers=auth_headers)
    assert messages.json()[0]["content"] == "Bom dia, preciso de ajuda"
    assert messages.json()[0]["direction"] == "inbound"

    process_jobs = await _jobs_named(session_factory, "whatsapp.process_inbound")
    assert len(process_jobs) == 1
    assert process_jobs[0].status == JobStatus.QUEUED

    # 4) Worker runs the whole due batch (memory.embed, workflow.trigger and
    # whatsapp.process_inbound all became due at once); memory.embed and
    # workflow.trigger fail in this test env (no real Qdrant/n8n) and simply
    # retry later — what matters is the AI Orchestrator ran end-to-end
    # (agent selection, memory, tool budget, reply) and queued the send.
    processed = await worker.run_once()
    assert processed == 3

    send_jobs = await _jobs_named(session_factory, "whatsapp.send_text")
    assert len(send_jobs) == 1
    assert send_jobs[0].payload["to"] == "5511977778888"
    assert send_jobs[0].payload["content"]  # the agent's reply text (stub, no LLM key in tests)

    # 5) Running the send job delivers through the provider AND persists +
    # feeds memory — the exact gap this phase closed in jobs/handlers.py.
    with _send_text_mock() as mocked_send:
        processed = await worker.run_once()
    assert processed == 1
    mocked_send.assert_awaited_once()

    async with session_factory() as session:
        outbound = (
            (await session.execute(select(Message).where(Message.direction == MessageDirection.OUTBOUND)))
            .scalars()
            .all()
        )
    assert len(outbound) == 1
    assert outbound[0].content == send_jobs[0].payload["content"]

    # Both jobs succeeded — nothing left dangling in the queue.
    async with session_factory() as session:
        statuses = {job.name: job.status for job in (await session.execute(select(Job))).scalars().all()}
    assert statuses["whatsapp.process_inbound"] == JobStatus.SUCCEEDED
    assert statuses["whatsapp.send_text"] == JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_auto_reply_acts_on_behalf_of_first_admin(client, auth_headers, session_factory, worker):
    """Tool calls from the WhatsApp flow need a User; Dario OS is single-owner,
    so they act on behalf of the first admin account, not the contact."""
    await client.post(
        "/api/webhooks/whatsapp",
        json={"from": "5511988889999@c.us", "body": "oi", "notifyName": "X", "id": "wamid-owner-1"},
    )
    await worker.run_once()

    async with session_factory() as session:
        owner = await UserRepository(session).get_first_admin()
    assert owner is not None
    assert owner.email == "dario@example.com"  # from the auth_headers fixture, the first registered user


@pytest.mark.asyncio
async def test_get_first_admin_with_multiple_admins_does_not_crash(session_factory):
    """find_one() would raise MultipleResultsFound with >1 admin; get_first_admin
    must tolerate that (and deterministically pick the earliest-created one)."""
    from models.user import User, UserRole

    async with session_factory() as session:
        first = User(email="admin1@example.com", full_name="A1", hashed_password="x", role=UserRole.ADMIN)
        second = User(email="admin2@example.com", full_name="A2", hashed_password="x", role=UserRole.ADMIN)
        session.add_all([first, second])
        await session.commit()

        owner = await UserRepository(session).get_first_admin()
    assert owner is not None
    assert owner.email == "admin1@example.com"


@pytest.mark.asyncio
async def test_pipeline_skips_auto_reply_without_any_registered_user(client, session_factory, worker):
    """No admin exists yet (fresh instance): the job must no-op, not crash."""
    await client.post(
        "/api/webhooks/whatsapp",
        json={"from": "5511999990001@c.us", "body": "oi", "notifyName": "Y", "id": "wamid-noadmin"},
    )
    await worker.run_once()

    async with session_factory() as session:
        job = (await session.execute(select(Job).where(Job.name == "whatsapp.process_inbound"))).scalar_one()
    assert job.status == JobStatus.SUCCEEDED  # no-op, not a failure
    send_jobs = await _jobs_named(session_factory, "whatsapp.send_text")
    assert send_jobs == []


@pytest.mark.asyncio
async def test_auto_reply_disabled_by_setting(client, auth_headers, session_factory, monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "auto_reply_enabled", False)
    await client.post(
        "/api/webhooks/whatsapp",
        json={"from": "5511911112223@c.us", "body": "oi", "notifyName": "Z", "id": "wamid-disabled"},
    )
    assert await _jobs_named(session_factory, "whatsapp.process_inbound") == []
    # The legacy n8n hand-off keeps working regardless of the setting.
    assert len(await _jobs_named(session_factory, "workflow.trigger")) == 1


@pytest.mark.asyncio
async def test_auto_reply_skipped_for_non_text_media(client, session_factory):
    await client.post(
        "/api/webhooks/whatsapp",
        json={
            "from": "5511922223334@c.us",
            "body": "",
            "notifyName": "Img",
            "id": "wamid-image",
            "type": "image",
        },
    )
    assert await _jobs_named(session_factory, "whatsapp.process_inbound") == []


@pytest.mark.asyncio
async def test_auto_reply_skipped_for_blank_text(client, session_factory):
    await client.post(
        "/api/webhooks/whatsapp",
        json={"from": "5511933334445@c.us", "body": "   ", "notifyName": "Blank", "id": "wamid-blank"},
    )
    assert await _jobs_named(session_factory, "whatsapp.process_inbound") == []


@pytest.mark.asyncio
async def test_loop_guard_throttles_auto_reply_per_contact(client, session_factory, monkeypatch):
    """Flood/loop protection: beyond the per-contact-per-minute threshold, no
    more auto-reply jobs are queued (the message itself is still persisted)."""
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "auto_reply_max_per_contact_per_minute", 2)

    for i in range(4):
        await client.post(
            "/api/webhooks/whatsapp",
            json={
                "from": "5511944445556@c.us",
                "body": f"mensagem {i}",
                "notifyName": "Loop",
                "id": f"wamid-loop-{i}",
            },
        )

    async with session_factory() as session:
        inbound = (
            (await session.execute(select(Message).where(Message.direction == MessageDirection.INBOUND)))
            .scalars()
            .all()
        )
    assert len(inbound) == 4  # every message is still recorded

    process_jobs = await _jobs_named(session_factory, "whatsapp.process_inbound")
    assert len(process_jobs) == 2  # only the first 2 within the window triggered a reply


@pytest.mark.asyncio
async def test_send_text_job_persists_and_feeds_memory(session_factory, worker):
    """Regression test for the gap this phase closed: the job-driven send
    (used by agent tool calls and the automatic reply) used to only call the
    provider and skip persistence/memory entirely."""
    from jobs.service import JobService

    async with session_factory() as session:
        contact = Contact(name="Direct", phone="5511955556667")
        session.add(contact)
        await session.commit()
        await JobService(session).enqueue(
            "whatsapp.send_text", {"to": "5511955556667", "content": "Olá direto da fila!"}
        )

    with _send_text_mock():
        processed = await worker.run_once()
    assert processed == 1

    async with session_factory() as session:
        outbound = (
            (await session.execute(select(Message).where(Message.direction == MessageDirection.OUTBOUND)))
            .scalars()
            .all()
        )
    assert len(outbound) == 1
    assert outbound[0].content == "Olá direto da fila!"


@pytest.mark.asyncio
async def test_apology_sent_after_auto_reply_job_exhausts_retries(session_factory, worker):
    """Safety net via the Event Bus: job.failed for whatsapp.process_inbound
    triggers an apology, so the contact is never left in silence."""
    from jobs.handlers import register_event_subscribers
    from jobs.registry import job_handler
    from jobs.service import JobService

    register_event_subscribers()

    # Force a real failure (instead of exercising the full orchestrator) to
    # drive the job to FAILED and trigger the job.failed event.
    @job_handler("whatsapp.process_inbound")
    async def _boom(db, payload):
        raise RuntimeError("simulated orchestrator crash")

    async with session_factory() as session:
        contact = Contact(name="Falha", phone="5511966667778")
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        job = await JobService(session).enqueue(
            "whatsapp.process_inbound",
            {"contact_id": contact.id, "message_id": 1},
            max_attempts=1,
        )

    await worker.run_once()

    async with session_factory() as session:
        refreshed = await session.get(Job, job.id)
        assert refreshed.status == JobStatus.FAILED

    send_jobs = await _jobs_named(session_factory, "whatsapp.send_text")
    assert len(send_jobs) == 1
    assert send_jobs[0].payload["to"] == "5511966667778"
    assert "problema" in send_jobs[0].payload["content"]
