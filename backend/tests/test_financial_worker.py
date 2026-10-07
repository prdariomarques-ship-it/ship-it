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
    async def _flaky(db, job):
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
    async def _handler(db, job):
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
    async def _handler(db, job):
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
            started_at=datetime.now(timezone.utc) - timedelta(seconds=600),
            lease_token="stale-lease", lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=300),
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


# ── telegram.send_message is excluded from the chain-uniqueness index ───────
# (regression test for the exact bug a review caught: the index used to
# apply to every job name, including this one, which every feed shares.)


@pytest.mark.asyncio
async def test_two_different_feeds_queue_without_colliding(session_factory):
    async with session_factory() as session:
        await FinancialJobRepository(session).create(
            name="telegram.send_message", payload={"feed": "spcx", "text": "a"}
        )
    async with session_factory() as session:
        # Must NOT raise DuplicateChainError — different feed, same job name.
        await FinancialJobRepository(session).create(
            name="telegram.send_message", payload={"feed": "b3", "text": "b"}
        )

    async with session_factory() as session:
        rows = (
            await session.execute(select(FinancialJob).where(FinancialJob.name == "telegram.send_message"))
        ).scalars().all()
        assert len(rows) == 2
        assert {r.payload["feed"] for r in rows} == {"spcx", "b3"}


@pytest.mark.asyncio
async def test_same_feed_can_have_several_pending_sends(session_factory):
    """A burst of real alerts for ONE feed must also be allowed to queue up
    as separate rows — the constraint is about chain names, not feeds."""
    async with session_factory() as session:
        repo = FinancialJobRepository(session)
        for i in range(3):
            await repo.create(name="telegram.send_message", payload={"feed": "spcx", "text": f"msg {i}"})

    async with session_factory() as session:
        rows = (
            await session.execute(select(FinancialJob).where(FinancialJob.name == "telegram.send_message"))
        ).scalars().all()
        assert len(rows) == 3


# ── recovery after a crash must never auto-resend an accepted message ───────


@pytest.mark.asyncio
async def test_stale_telegram_send_job_is_not_auto_retried(session_factory, worker, monkeypatch):
    """If the process crashes after Telegram already accepted the message
    but before the result was persisted, recovery must mark it uncertain
    and stop — never silently requeue it for a second attempt."""
    from datetime import datetime, timedelta, timezone

    send_calls = []

    @financial_job_handler("telegram.send_message")
    async def _handler(db, job):
        send_calls.append(job.payload)
        return {"delivered": True, "message_id": 1}

    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(
            name="telegram.send_message", payload={"feed": "spcx", "text": "oi"}, max_attempts=3
        )
        repo = FinancialJobRepository(session)
        existing = await repo.get(job.id)
        await repo.update(
            existing, status=FinancialJobStatus.RUNNING,
            started_at=datetime.now(timezone.utc) - timedelta(seconds=600),
            lease_token="stale-lease", lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=300),
            attempts=1,
        )

    await worker.run_once()  # recovery runs at the top of every tick

    assert send_calls == []  # the handler was never invoked again

    async with session_factory() as session:
        refreshed = await FinancialJobRepository(session).get(job.id)
        assert refreshed.status == FinancialJobStatus.FAILED
        assert refreshed.result == {"delivered": None, "reason": "uncertain_outcome_process_crash"}


# ── self-healing: a chain that dies between its two commits heals itself ────


@pytest.mark.asyncio
async def test_a_missing_chain_is_reseeded_on_the_next_tick_without_a_restart(session_factory, worker, monkeypatch):
    """Simulates exactly the gap the review asked about: the current row
    already SUCCEEDED, but the successor was never created (process died,
    or the create() call itself failed) — the very next tick must recreate
    it, with no process restart and no second chain."""
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "market_monitors_enabled", True)

    # A trivial fake handler: the re-seeded row is due immediately (delay 0)
    # and would otherwise be claimed+executed within this same tick by the
    # real check_spcx34_job, which calls out to Yahoo Finance for real.
    @financial_job_handler("market.check_spcx34")
    async def _fake_check(db, job):
        return None

    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(name="market.check_spcx34", payload={})
        repo = FinancialJobRepository(session)
        existing = await repo.get(job.id)
        # The chain's only row is already terminal — as if the successor
        # create() never happened after marking this one SUCCEEDED.
        await repo.update(existing, status=FinancialJobStatus.SUCCEEDED)

    await worker.run_once()  # ensure_chains_seeded runs at the top of every tick

    async with session_factory() as session:
        rows = (
            await session.execute(select(FinancialJob).where(FinancialJob.name == "market.check_spcx34"))
        ).scalars().all()
        queued = [r for r in rows if r.status == FinancialJobStatus.QUEUED]
        assert len(queued) == 1  # healed, and exactly one — not a duplicate chain


@pytest.mark.asyncio
async def test_healing_does_not_touch_a_chain_that_is_already_active(session_factory, worker, monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "market_monitors_enabled", True)

    async with session_factory() as session:
        # Scheduled in the future, so _claim_due leaves it alone this tick —
        # isolates ensure_chains_seeded's behavior from claim/execute.
        await FinancialJobRepository(session).create(
            name="market.check_spcx34", payload={}, delay_seconds=3600
        )

    await worker.run_once()

    async with session_factory() as session:
        rows = (
            await session.execute(select(FinancialJob).where(FinancialJob.name == "market.check_spcx34"))
        ).scalars().all()
        assert len(rows) == 1  # healing must not create a second row when one is already active


# ── ownership/lease: two recoveries racing the same stale job ───────────────


@pytest.mark.asyncio
async def test_two_concurrent_recoveries_only_one_wins(session_factory):
    """Simulates two worker processes both reading the same stale candidate
    and both attempting to recover it — exactly the race the review asked
    about. Both READ the same lease_token (as two real processes would,
    each via its own stale_running_candidates() call); only the FIRST
    try_recover_stale() may succeed, since it's an atomic
    UPDATE...WHERE lease_token=:token — the second's WHERE clause no
    longer matches anything once the first has already changed the row."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(name="market.check_spcx34", payload={}, max_attempts=3)
        repo = FinancialJobRepository(session)
        existing = await repo.get(job.id)
        await repo.update(
            existing, status=FinancialJobStatus.RUNNING, started_at=now - timedelta(seconds=600),
            lease_token="shared-lease", lease_expires_at=now - timedelta(seconds=300), attempts=1,
        )

    # Two "processes": each opens its own session/repository, both read the
    # same lease_token (as stale_running_candidates would independently
    # hand each of them), then both race to recover it.
    async with session_factory() as session_a, session_factory() as session_b:
        repo_a, repo_b = FinancialJobRepository(session_a), FinancialJobRepository(session_b)
        won_a = await repo_a.try_recover_stale(
            job.id, "shared-lease", now, failed=False, last_error="recovered by A"
        )
        won_b = await repo_b.try_recover_stale(
            job.id, "shared-lease", now, failed=False, last_error="recovered by B"
        )

    assert [won_a, won_b].count(True) == 1  # exactly one recovery wins, never both, never neither

    async with session_factory() as session:
        refreshed = await FinancialJobRepository(session).get(job.id)
        assert refreshed.status == FinancialJobStatus.QUEUED
        assert refreshed.last_error in ("recovered by A", "recovered by B")


@pytest.mark.asyncio
async def test_reclaimed_job_cannot_be_clobbered_by_the_original_slow_execution(session_factory, worker):
    """A slow-but-still-alive execution's lease expires and gets reclaimed
    by a recovery (so the row now belongs to a NEW lease/attempt). The
    ORIGINAL execution then finally finishes and tries to write its
    result — complete_if_owner must refuse (its lease_token is stale), so
    it can never clobber whatever the new owner does with the row."""
    from datetime import datetime, timezone

    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(name="test.slow", payload={})
        repo = FinancialJobRepository(session)
        existing = await repo.get(job.id)
        await repo.update(existing, status=FinancialJobStatus.RUNNING, lease_token="original-lease")

    # Simulate a recovery reclaiming it (new lease, now QUEUED again).
    async with session_factory() as session:
        repo = FinancialJobRepository(session)
        recovered = await repo.try_recover_stale(
            job.id, "original-lease", datetime.now(timezone.utc), failed=False, last_error="reclaimed"
        )
        assert recovered is True

    # The ORIGINAL (stale) execution now finally finishes and tries to
    # write its result under its now-superseded lease token.
    async with session_factory() as session:
        repo = FinancialJobRepository(session)
        completed = await repo.complete_if_owner(
            job.id, "original-lease", status=FinancialJobStatus.SUCCEEDED,
            finished_at=datetime.now(timezone.utc), result={"from": "stale execution"},
        )
        assert completed is False  # refused: lease no longer matches

    async with session_factory() as session:
        refreshed = await FinancialJobRepository(session).get(job.id)
        # Still in the state the recovery put it in — untouched by the stale write.
        assert refreshed.status == FinancialJobStatus.QUEUED
        assert refreshed.result is None


# ── cadence: successor creation is atomic with marking the current row done ─


@pytest.mark.asyncio
async def test_complete_and_reschedule_is_one_transaction(session_factory):
    """complete_and_reschedule marks SUCCEEDED and creates the successor
    together — there is no committed intermediate state where the current
    row is terminal but no successor exists yet for another process's
    healing pass to react to (which is what let a concurrent
    ensure_chains_seeded call insert an off-cadence immediate successor,
    before this fix)."""
    from datetime import datetime, timezone

    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(name="market.check_spcx34", payload={})
        repo = FinancialJobRepository(session)
        existing = await repo.get(job.id)
        await repo.update(existing, status=FinancialJobStatus.RUNNING, lease_token="lease-1")

    async with session_factory() as session:
        repo = FinancialJobRepository(session)
        completed, rescheduled = await repo.complete_and_reschedule(
            job.id, "lease-1", result={"ok": True}, finished_at=datetime.now(timezone.utc),
            reschedule_name="market.check_spcx34", reschedule_delay_seconds=1200,
        )
        assert completed is True
        assert rescheduled is True

    async with session_factory() as session:
        rows = (
            await session.execute(select(FinancialJob).where(FinancialJob.name == "market.check_spcx34"))
        ).scalars().all()
        assert len(rows) == 2
        succeeded = [r for r in rows if r.status == FinancialJobStatus.SUCCEEDED]
        queued = [r for r in rows if r.status == FinancialJobStatus.QUEUED]
        assert len(succeeded) == 1 and len(queued) == 1
        # The successor respects the full 1200s cadence, not an immediate requeue.
        delay = (queued[0].scheduled_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds()
        assert delay > 1000


@pytest.mark.asyncio
async def test_complete_and_reschedule_refuses_a_stale_lease_and_creates_no_successor(session_factory):
    from datetime import datetime, timezone

    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(name="market.check_spcx34", payload={})
        repo = FinancialJobRepository(session)
        existing = await repo.get(job.id)
        await repo.update(existing, status=FinancialJobStatus.RUNNING, lease_token="real-lease")

    async with session_factory() as session:
        repo = FinancialJobRepository(session)
        completed, rescheduled = await repo.complete_and_reschedule(
            job.id, "wrong-lease", result={"ok": True}, finished_at=datetime.now(timezone.utc),
            reschedule_name="market.check_spcx34", reschedule_delay_seconds=1200,
        )
        assert completed is False
        assert rescheduled is False

    async with session_factory() as session:
        rows = (
            await session.execute(select(FinancialJob).where(FinancialJob.name == "market.check_spcx34"))
        ).scalars().all()
        assert len(rows) == 1  # no successor was created for a completion that didn't happen


# ── report idempotency: a retried generator must not duplicate its report ───


@pytest.mark.asyncio
async def test_retried_generator_does_not_duplicate_its_telegram_report(session_factory, worker, monkeypatch):
    """The exact crash the review described: the generator successfully
    enqueues its telegram.send_message, then (simulated here, since the
    real sequence spans two DB writes) gets treated as if it crashed and
    got retried before marking itself done. Re-running the SAME generator
    job id must not produce a second report."""
    from investments.jobs import SPCX34_JOB_NAME, _enqueue_telegram
    from investments.spcx34_monitor import SPCX34Check

    async with session_factory() as session:
        job = await FinancialJobRepository(session).create(name=SPCX34_JOB_NAME, payload={})

    # First "attempt": the generator produces its report.
    async with session_factory() as session:
        created = await _enqueue_telegram(session, "spcx", "primeira tentativa", idempotency_key=f"spcx:{job.id}")
        assert created is True

    # Second "attempt" of the SAME generator job id (as a retry after a
    # crash would be) tries to produce the same report again.
    async with session_factory() as session:
        created_again = await _enqueue_telegram(
            session, "spcx", "segunda tentativa (retry)", idempotency_key=f"spcx:{job.id}"
        )
        assert created_again is False  # rejected: already produced

    async with session_factory() as session:
        rows = (
            await session.execute(select(FinancialJob).where(FinancialJob.name == "telegram.send_message"))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].payload["text"] == "primeira tentativa"  # the retry's text never landed


@pytest.mark.asyncio
async def test_different_generator_attempts_get_different_idempotency_keys(session_factory):
    """Two DIFFERENT generator job rows (e.g. two different check cycles)
    must each be free to produce their own report — idempotency is scoped
    to one generator job id, not to the feed as a whole."""
    from investments.jobs import SPCX34_JOB_NAME, _enqueue_telegram

    async with session_factory() as session:
        job_1 = await FinancialJobRepository(session).create(name=SPCX34_JOB_NAME, payload={})
    async with session_factory() as session:
        repo = FinancialJobRepository(session)
        existing = await repo.get(job_1.id)
        await repo.update(existing, status=FinancialJobStatus.SUCCEEDED)
    async with session_factory() as session:
        job_2 = await FinancialJobRepository(session).create(name=SPCX34_JOB_NAME, payload={})

    async with session_factory() as session:
        assert await _enqueue_telegram(session, "spcx", "cycle 1", idempotency_key=f"spcx:{job_1.id}") is True
    async with session_factory() as session:
        assert await _enqueue_telegram(session, "spcx", "cycle 2", idempotency_key=f"spcx:{job_2.id}") is True

    async with session_factory() as session:
        rows = (
            await session.execute(select(FinancialJob).where(FinancialJob.name == "telegram.send_message"))
        ).scalars().all()
        assert len(rows) == 2
