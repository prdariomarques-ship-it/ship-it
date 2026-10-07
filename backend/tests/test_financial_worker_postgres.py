"""Real-Postgres concurrency/recovery/cadence/idempotency tests for the
financial job queue.

Why this file exists, separate from test_financial_worker.py: that file
runs against SQLite (StaticPool, one shared connection) and simulates
concurrency with asyncio.gather on the SAME event loop. That's enough to
exercise the application-level logic (lease checks, atomic UPDATEs,
SAVEPOINTs) but it CANNOT exercise real Postgres row locking —
`with_for_update(skip_locked=True)` is silently dropped by SQLAlchemy's
SQLite dialect, and SQLite's single-writer model makes two true concurrent
claimers structurally impossible there regardless. The review (point 6)
is correct that this is a real gap: SQLite-and-gather tests validate the
code's logic, not Postgres's actual locking behavior under it.

This file closes that gap using a REAL local Postgres (asyncpg), with
truly independent connections/sessions standing in for separate worker
processes claiming/recovering/completing the same rows concurrently.

Gating — this suite NEVER runs against the VPS or any shared database:
  - It only runs if TEST_POSTGRES_URL is set in the environment, pointing
    at a disposable database. It is never set in CI or in this sandbox by
    default — every test is skipped (not failed, not faked) when absent.
  - It never reads DATABASE_URL (the app's own setting) for this purpose,
    specifically so a misconfigured environment variable can't make this
    suite accidentally point at a real/shared database.
  - It drops and recreates the financial_jobs/alembic tables inside
    whatever database TEST_POSTGRES_URL names, every run — pointing this
    at anything other than a disposable test database will lose data.

What actually ran in this sandbox at the final commit: see the test
matrix in the review response. If TEST_POSTGRES_URL was unset, pytest's
own summary line for this file will say "skipped", not "passed" — that
is the honest, intended outcome absent an explicit, disposable Postgres
to point at.
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.base import Base
from investments.models import FinancialJob, FinancialJobStatus
from investments.repository import FinancialJobRepository
from investments.worker import Reschedule

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason=(
        "TEST_POSTGRES_URL not set — real-Postgres concurrency tests are "
        "NOT EXECUTED. Point it at a disposable local/throwaway Postgres "
        "database to run this suite; never at the VPS or any shared "
        "database. See this file's module docstring."
    ),
)


@pytest.fixture
async def pg_engine():
    engine = create_async_engine(TEST_POSTGRES_URL, pool_size=10, max_overflow=0)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def pg_session_factory(pg_engine):
    return async_sessionmaker(pg_engine, expire_on_commit=False)


def _independent_session_factory():
    """A second engine/sessionmaker with its own connection pool — stands
    in for a second OS process, so two 'workers' in a test never share a
    connection (which would make lock contention artificial)."""
    engine = create_async_engine(TEST_POSTGRES_URL, pool_size=5, max_overflow=0)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


# ── point 1: exclusive recovery — real row locking, two real connections ───


@pytest.mark.asyncio
async def test_claim_due_skip_locked_never_double_claims_under_real_postgres(pg_session_factory):
    """The exact guarantee SQLite can't exercise: two real, independent
    connections both calling claim_due() concurrently against the SAME
    due row must never both receive it. With SKIP LOCKED actually honored
    by Postgres (not silently dropped), one must get the row and the
    other must get an empty list for that same claim call."""
    async with pg_session_factory() as setup_session:
        job = FinancialJob(name="telegram.send_message", payload={}, scheduled_at=datetime.now(timezone.utc))
        setup_session.add(job)
        await setup_session.commit()
        job_id = job.id

    engine_a, factory_a = _independent_session_factory()
    engine_b, factory_b = _independent_session_factory()
    try:
        async def claim(factory):
            async with factory() as session:
                repository = FinancialJobRepository(session)
                return await repository.claim_due(datetime.now(timezone.utc), limit=10)

        results_a, results_b = await asyncio.gather(claim(factory_a), claim(factory_b))
        claimed_ids = [j.id for j in results_a] + [j.id for j in results_b]
        assert claimed_ids.count(job_id) == 1, (
            f"job {job_id} was claimed {claimed_ids.count(job_id)} times across two concurrent "
            "connections — SKIP LOCKED did not prevent a double-claim"
        )
    finally:
        await engine_a.dispose()
        await engine_b.dispose()


@pytest.mark.asyncio
async def test_two_real_connections_racing_to_recover_the_same_stale_job(pg_session_factory):
    """Same guarantee as test_financial_worker.py's
    test_two_concurrent_recoveries_only_one_wins, but across two real,
    independent Postgres connections instead of asyncio.gather on a
    shared SQLite connection — confirms the atomic UPDATE...WHERE
    lease_token=:token actually serializes under real MVCC/row locking,
    not just under Python's cooperative scheduling."""
    now = datetime.now(timezone.utc)
    lease = uuid.uuid4().hex
    async with pg_session_factory() as setup_session:
        job = FinancialJob(
            name="market.check_spcx34", payload={}, status=FinancialJobStatus.RUNNING,
            started_at=now - timedelta(seconds=600), attempts=1, max_attempts=3,
            lease_token=lease, lease_expires_at=now - timedelta(seconds=300),
        )
        setup_session.add(job)
        await setup_session.commit()
        job_id = job.id

    engine_a, factory_a = _independent_session_factory()
    engine_b, factory_b = _independent_session_factory()
    try:
        async def recover(factory):
            async with factory() as session:
                repository = FinancialJobRepository(session)
                return await repository.try_recover_stale(
                    job_id, lease, datetime.now(timezone.utc), failed=False, last_error="recovered"
                )

        won_a, won_b = await asyncio.gather(recover(factory_a), recover(factory_b))
        assert [won_a, won_b].count(True) == 1
    finally:
        await engine_a.dispose()
        await engine_b.dispose()


# ── point 2: cadence — successor's scheduled_at under concurrent healing ───


@pytest.mark.asyncio
async def test_cadence_preserved_when_a_concurrent_healing_pass_races_completion(pg_session_factory):
    """The race the review described concretely: one connection finishes a
    chain job and calls complete_and_reschedule (SUCCEEDED + successor in
    one transaction); AT THE SAME TIME, a second connection's
    ensure_chains_seeded healing pass tries to insert its own immediate
    (delay_seconds=0) successor for the same chain name. Expected: exactly
    one QUEUED successor exists afterwards, and it carries the FULL
    configured delay — not an immediate/off-cadence one. The unique
    partial index is what makes this true even under real concurrent
    commits, not just under single-threaded SQLite."""
    now = datetime.now(timezone.utc)
    lease = uuid.uuid4().hex
    async with pg_session_factory() as setup_session:
        job = FinancialJob(
            name="market.check_spcx34", payload={}, status=FinancialJobStatus.RUNNING,
            started_at=now, attempts=1, max_attempts=3, lease_token=lease,
            lease_expires_at=now + timedelta(seconds=300),
        )
        setup_session.add(job)
        await setup_session.commit()
        job_id = job.id

    engine_a, factory_a = _independent_session_factory()
    engine_b, factory_b = _independent_session_factory()
    try:
        async def complete():
            async with factory_a() as session:
                repository = FinancialJobRepository(session)
                return await repository.complete_and_reschedule(
                    job_id, lease, result=None, finished_at=datetime.now(timezone.utc),
                    reschedule_name="market.check_spcx34", reschedule_delay_seconds=1200,
                )

        async def heal():
            async with factory_b() as session:
                repository = FinancialJobRepository(session)
                try:
                    await repository.create(name="market.check_spcx34", payload={}, delay_seconds=0)
                    return True
                except Exception:
                    return False

        await asyncio.gather(complete(), heal())

        async with pg_session_factory() as session:
            repository = FinancialJobRepository(session)
            rows = await repository.list(name="market.check_spcx34", limit=50)
        queued = [r for r in rows if r.status == FinancialJobStatus.QUEUED]
        assert len(queued) == 1, f"expected exactly one QUEUED successor, found {len(queued)}"
        delay = (queued[0].scheduled_at - now).total_seconds()
        assert delay > 1000, f"successor was scheduled only {delay}s out — cadence was not preserved"
    finally:
        await engine_a.dispose()
        await engine_b.dispose()


# ── point 3: idempotency — real unique constraint under concurrent insert ──


@pytest.mark.asyncio
async def test_idempotency_key_unique_constraint_holds_under_concurrent_insert(pg_session_factory):
    """Two real connections both try to create the SAME report (same
    idempotency_key) at the same instant — simulating a retried generator
    racing its own original (recovered) attempt. Exactly one must
    succeed; Postgres's unique index is the actual enforcement
    mechanism, not application-level check-then-insert (which would have
    a race window of its own)."""
    key = f"spcx:{uuid.uuid4().hex}"
    engine_a, factory_a = _independent_session_factory()
    engine_b, factory_b = _independent_session_factory()
    try:
        async def create(factory, text):
            async with factory() as session:
                repository = FinancialJobRepository(session)
                try:
                    await repository.create(
                        name="telegram.send_message", payload={"feed": "spcx", "text": text},
                        idempotency_key=key,
                    )
                    return True
                except Exception:
                    return False

        created_a, created_b = await asyncio.gather(
            create(factory_a, "primeira"), create(factory_b, "segunda")
        )
        assert [created_a, created_b].count(True) == 1

        async with pg_session_factory() as session:
            repository = FinancialJobRepository(session)
            rows = await repository.list(name="telegram.send_message", limit=50)
        matching = [r for r in rows if r.idempotency_key == key]
        assert len(matching) == 1
    finally:
        await engine_a.dispose()
        await engine_b.dispose()


# ── crash-between-commits: complete_and_reschedule's atomicity ─────────────


@pytest.mark.asyncio
async def test_complete_and_reschedule_is_atomic_against_a_concurrent_reader(pg_session_factory):
    """A concurrent reader must never observe the row SUCCEEDED without
    its successor already existing — that specific intermediate state is
    exactly what used to let a healing pass insert an off-cadence
    successor. Polls from a second, independent connection throughout the
    write; every observation must be all-or-nothing."""
    now = datetime.now(timezone.utc)
    lease = uuid.uuid4().hex
    async with pg_session_factory() as setup_session:
        job = FinancialJob(
            name="market.check_spcx34", payload={}, status=FinancialJobStatus.RUNNING,
            started_at=now, attempts=1, max_attempts=3, lease_token=lease,
            lease_expires_at=now + timedelta(seconds=300),
        )
        setup_session.add(job)
        await setup_session.commit()
        job_id = job.id

    engine_a, factory_a = _independent_session_factory()
    engine_b, factory_b = _independent_session_factory()
    observed_bad_state = False
    stop = asyncio.Event()

    async def writer():
        async with factory_a() as session:
            repository = FinancialJobRepository(session)
            await repository.complete_and_reschedule(
                job_id, lease, result=None, finished_at=datetime.now(timezone.utc),
                reschedule_name="market.check_spcx34", reschedule_delay_seconds=1200,
            )
        stop.set()

    async def reader():
        nonlocal observed_bad_state
        async with factory_b() as session:
            repository = FinancialJobRepository(session)
            while not stop.is_set():
                current = await repository.get(job_id)
                if current is not None and current.status == FinancialJobStatus.SUCCEEDED:
                    successors = await repository.list(name="market.check_spcx34", limit=50)
                    queued = [s for s in successors if s.status == FinancialJobStatus.QUEUED]
                    if not queued:
                        observed_bad_state = True
                await asyncio.sleep(0)

    try:
        await asyncio.gather(writer(), reader())
        assert not observed_bad_state, (
            "a concurrent reader observed the job SUCCEEDED with no successor yet queued — "
            "complete_and_reschedule is not atomic from an external reader's point of view"
        )
    finally:
        await engine_a.dispose()
        await engine_b.dispose()
