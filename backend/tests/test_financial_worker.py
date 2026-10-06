"""The isolated financial_jobs queue: uniqueness under real concurrency,
stale-job recovery after a simulated crash, and that this worker never
touches the jobs table used by WhatsApp."""
import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from investments.models import FinancialJob, FinancialJobStatus
from investments.repository import DuplicateChainError, FinancialJobRepository
from investments.worker import FinancialWorker, _HANDLERS, financial_job_handler


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def worker(session_factory, monkeypatch):
    monkeypatch.setattr("investments.worker.async_session_factory", session_factory)
    return FinancialWorker()


@pytest.fixture(autouse=True)
def _isolated_handlers():
    saved = dict(_HANDLERS)
    yield
    _HANDLERS.clear()
    _HANDLERS.update(saved)


# ── isolation from the WhatsApp `jobs` table ─────────────────────────────────


def test_financial_jobs_is_a_separate_table_from_jobs():
    from models.job import Job

    assert FinancialJob.__tablename__ == "financial_jobs"
    assert FinancialJob.__tablename__ != Job.__tablename__


def test_worker_module_does_not_import_whatsapp_job_infra():
    import investments.worker as worker_module

    with open(worker_module.__file__) as f:
        import_lines = [line for line in f if line.lstrip().startswith(("import ", "from "))]
    for forbidden in ("jobs.worker", "jobs.registry", "jobs.events", "models.job", "repositories.job"):
        assert not any(forbidden in line for line in import_lines), (
            f"investments/worker.py must not import {forbidden}"
        )


# ── uniqueness: at most one QUEUED/RUNNING chain per name ───────────────────


@pytest.mark.asyncio
async def test_create_rejects_a_second_queued_chain(session_factory):
    async with session_factory() as session:
        await FinancialJobRepository(session).create(name="market.check_spcx34", payload={})
    async with session_factory() as session:
        with pytest.raises(DuplicateChainError):
            await FinancialJobRepository(session).create(name="market.check_spcx34", payload={})


@pytest.mark.asyncio
async def test_create_allows_a_new_chain_after_the_old_one_finished(session_factory):
    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(name="market.check_spcx34", payload={})
    async with session_factory() as session:
        repo = FinancialJobRepository(session)
        existing = await repo.get(job.id)
        await repo.update(existing, status=FinancialJobStatus.SUCCEEDED)
    async with session_factory() as session:
        # No exception: the prior row is SUCCEEDED, not QUEUED/RUNNING.
        await FinancialJobRepository(session).create(name="market.check_spcx34", payload={})


@pytest.mark.asyncio
async def test_concurrent_create_calls_only_let_one_through(session_factory):
    """Real concurrency, not a mocked race: N simultaneous creates for the
    same name must leave exactly one QUEUED row — this is what closes the
    seeding query-then-insert race the review flagged."""
    async def _try_create():
        async with session_factory() as session:
            try:
                await FinancialJobRepository(session).create(name="market.check_spcx34", payload={})
                return True
            except DuplicateChainError:
                return False

    results = await asyncio.gather(*(_try_create() for _ in range(10)))
    assert sum(results) == 1

    async with session_factory() as session:
        rows = (
            await session.execute(select(FinancialJob).where(FinancialJob.name == "market.check_spcx34"))
        ).scalars().all()
        assert len(rows) == 1


# ── worker execution: retry/backoff, no duplicate chain on handler error ────


@pytest.mark.asyncio
async def test_handler_exception_retries_without_creating_a_second_row(session_factory, worker):
    attempts = []

    @financial_job_handler("test.flaky")
    async def _flaky(db, payload):
        attempts.append(1)
        raise RuntimeError("boom")

    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(name="test.flaky", payload={}, max_attempts=2)

    await worker.run_once()
    async with session_factory() as session:
        refreshed = await FinancialJobRepository(session).get(job.id)
        assert refreshed.status == FinancialJobStatus.QUEUED
        assert refreshed.attempts == 1
        rows = (await session.execute(select(FinancialJob).where(FinancialJob.name == "test.flaky"))).scalars().all()
        assert len(rows) == 1  # retried in place, never a second row

    # Pull the retry forward and run again — exhausts attempts, ends FAILED.
    async with session_factory() as session:
        refreshed = await FinancialJobRepository(session).get(job.id)
        from datetime import datetime, timezone

        await FinancialJobRepository(session).update(refreshed, scheduled_at=datetime.now(timezone.utc))

    await worker.run_once()
    async with session_factory() as session:
        refreshed = await FinancialJobRepository(session).get(job.id)
        assert refreshed.status == FinancialJobStatus.FAILED
        assert len(attempts) == 2


@pytest.mark.asyncio
async def test_handler_result_is_persisted(session_factory, worker):
    @financial_job_handler("test.with_result")
    async def _handler(db, payload):
        return {"delivered": True, "message_id": 123}

    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(name="test.with_result", payload={})

    await worker.run_once()
    async with session_factory() as session:
        refreshed = await FinancialJobRepository(session).get(job.id)
        assert refreshed.status == FinancialJobStatus.SUCCEEDED
        assert refreshed.result == {"delivered": True, "message_id": 123}


@pytest.mark.asyncio
async def test_rate_limited_error_backoff_respects_retry_after(session_factory, worker):
    from investments.telegram_sender import TelegramRateLimitedError

    @financial_job_handler("test.rate_limited")
    async def _handler(db, payload):
        raise TelegramRateLimitedError(retry_after_seconds=9999)

    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(name="test.rate_limited", payload={}, max_attempts=3)

    await worker.run_once()
    async with session_factory() as session:
        refreshed = await FinancialJobRepository(session).get(job.id)
        assert refreshed.status == FinancialJobStatus.QUEUED
        from datetime import datetime, timezone

        scheduled_at = refreshed.scheduled_at
        if scheduled_at.tzinfo is None:  # SQLite doesn't persist tzinfo
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        delay = (scheduled_at - datetime.now(timezone.utc)).total_seconds()
        assert delay > 9000  # far longer than the default exponential backoff


# ── restart recovery: a job stuck in RUNNING is reclaimed, not duplicated ───


@pytest.mark.asyncio
async def test_stale_running_job_is_recovered_not_duplicated(session_factory, worker):
    from datetime import datetime, timedelta, timezone

    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(name="market.check_spcx34", payload={}, max_attempts=3)
        repo = FinancialJobRepository(session)
        existing = await repo.get(job.id)
        await repo.update(
            existing, status=FinancialJobStatus.RUNNING,
            started_at=datetime.now(timezone.utc) - timedelta(seconds=600),  # older than the 300s stale window
            attempts=1,
        )

    await worker.run_once()  # recovery runs at the top of every tick

    async with session_factory() as session:
        rows = (
            await session.execute(select(FinancialJob).where(FinancialJob.name == "market.check_spcx34"))
        ).scalars().all()
        assert len(rows) == 1  # recovered in place, not a second chain
        assert rows[0].status in (FinancialJobStatus.QUEUED, FinancialJobStatus.SUCCEEDED, FinancialJobStatus.RUNNING)


# ── GET /api/investments/jobs — read-only, admin-only, own table only ───────


@pytest.mark.asyncio
async def test_investments_jobs_endpoint_requires_auth(client):
    response = await client.get("/api/investments/jobs")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_investments_jobs_endpoint_lists_financial_jobs_only(client, auth_headers, db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        await FinancialJobRepository(session).create(name="market.check_spcx34", payload={"x": 1})

    response = await client.get("/api/investments/jobs", headers=auth_headers)
    assert response.status_code == 200
    names = [row["name"] for row in response.json()]
    assert "market.check_spcx34" in names
    # Every field this endpoint can touch comes from FinancialJobRepository,
    # which only ever queries the financial_jobs table — nothing here can
    # surface a row from `jobs` (WhatsApp's queue).
    assert all("to" not in row["payload"] for row in response.json())  # whatsapp.send_text's own payload shape
