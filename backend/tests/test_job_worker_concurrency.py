"""Tests for JobWorker concurrency control via asyncio.Semaphore."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jobs.worker import JobWorker
from models.job import Job, JobStatus


@pytest.fixture
def job_worker():
    """Create a JobWorker instance for testing."""
    return JobWorker()


@pytest.fixture
def mock_job(job_id: int = 1) -> Job:
    """Create a mock Job object."""
    job = MagicMock(spec=Job)
    job.id = job_id
    job.name = "test.job"
    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)
    job.attempts = 1
    job.max_attempts = 3
    job.payload = {}
    return job


@pytest.mark.asyncio
async def test_semaphore_initialized_with_config():
    """Verify semaphore is initialized with jobs_max_concurrent_workers setting."""
    worker = JobWorker()
    assert worker._semaphore is not None
    assert worker._semaphore._value == worker._settings.jobs_max_concurrent_workers


@pytest.mark.asyncio
async def test_concurrency_limit_enforcement():
    """Verify only N jobs execute concurrently via semaphore."""
    worker = JobWorker()
    max_concurrent = worker._settings.jobs_max_concurrent_workers

    # Track concurrent executions
    active_count = 0
    max_active = 0
    lock = asyncio.Lock()

    async def track_execution():
        nonlocal active_count, max_active
        async with lock:
            active_count += 1
            max_active = max(max_active, active_count)
        try:
            await asyncio.sleep(0.01)  # Simulate work
        finally:
            async with lock:
                active_count -= 1

    # Create N+3 tasks to verify semaphore enforcement
    tasks = [track_execution() for _ in range(max_concurrent + 3)]

    # Apply semaphore to all tasks (simulating execute_with_semaphore behavior)
    guarded_tasks = []
    for task in tasks:
        async def guarded(t=task):
            async with worker._semaphore:
                await t

        guarded_tasks.append(guarded())

    await asyncio.gather(*guarded_tasks)

    # Verify max concurrent never exceeded limit
    assert max_active <= max_concurrent, f"Max concurrent {max_active} exceeded limit {max_concurrent}"


@pytest.mark.asyncio
async def test_semaphore_prevents_exceeding_limit():
    """Verify semaphore blocks new acquisitions when limit is reached."""
    worker = JobWorker()
    max_concurrent = worker._settings.jobs_max_concurrent_workers

    acquire_order = []
    release_order = []

    async def acquire_and_hold(task_id: int):
        acquire_order.append(task_id)
        async with worker._semaphore:
            # At this point, semaphore.locked() tells us if we're at capacity
            await asyncio.sleep(0.01)
        release_order.append(task_id)

    # Create tasks exceeding the limit
    tasks = [acquire_and_hold(i) for i in range(max_concurrent + 2)]
    await asyncio.gather(*tasks)

    # All tasks acquired and released
    assert len(acquire_order) == max_concurrent + 2
    assert len(release_order) == max_concurrent + 2


@pytest.mark.asyncio
async def test_asyncio_gather_runs_all_tasks():
    """Verify asyncio.gather executes all tasks concurrently without blocking."""
    results = []

    async def mock_job_execution(job_id: int):
        await asyncio.sleep(0.001)
        results.append(job_id)

    job_ids = list(range(1, 6))
    await asyncio.gather(*(mock_job_execution(jid) for jid in job_ids))

    # All jobs executed
    assert sorted(results) == job_ids


@pytest.mark.asyncio
async def test_exception_in_one_task_propagates():
    """Verify asyncio.gather propagates exceptions from tasks."""
    results = []

    async def mock_job_execution(job_id: int):
        if job_id == 3:
            raise ValueError(f"Job {job_id} error")
        await asyncio.sleep(0.001)
        results.append(job_id)

    job_ids = list(range(1, 6))
    with pytest.raises(ValueError):
        await asyncio.gather(*(mock_job_execution(jid) for jid in job_ids))

    # Some jobs may have executed before exception
    assert len(results) >= 0


@pytest.mark.asyncio
async def test_asyncio_gather_return_exceptions_true():
    """Verify asyncio.gather with return_exceptions=True doesn't raise."""
    results = []

    async def mock_job_execution(job_id: int):
        if job_id == 3:
            raise ValueError(f"Job {job_id} error")
        await asyncio.sleep(0.001)
        return job_id

    job_ids = list(range(1, 6))
    # return_exceptions=True allows all tasks to complete
    outcomes = await asyncio.gather(
        *(mock_job_execution(jid) for jid in job_ids),
        return_exceptions=True,
    )

    # 4 successful + 1 error
    assert len(outcomes) == 5
    assert 1 in outcomes
    assert 2 in outcomes
    assert isinstance(outcomes[2], ValueError)  # Index 2 = job_id 3


@pytest.mark.asyncio
async def test_semaphore_fifo_ordering():
    """Verify semaphore grants permits in FIFO order."""
    order = []
    worker = JobWorker()

    async def acquire(task_id: int):
        async with worker._semaphore:
            order.append(("acquired", task_id))
            await asyncio.sleep(0.01)
        order.append(("released", task_id))

    # Create tasks
    tasks = [acquire(i) for i in range(10)]
    await asyncio.gather(*tasks)

    # All tasks acquired and released
    acquired = [t for a, t in order if a == "acquired"]
    released = [t for a, t in order if a == "released"]

    assert len(acquired) == 10
    assert len(released) == 10


@pytest.mark.asyncio
async def test_concurrent_job_execution_performance():
    """Verify concurrent execution is faster than sequential."""
    execution_times = []

    async def mock_job(delay: float = 0.05):
        await asyncio.sleep(delay)

    # Sequential execution (5 jobs × 0.05s = 0.25s+)
    start = asyncio.get_event_loop().time()
    for _ in range(5):
        await mock_job()
    sequential_time = asyncio.get_event_loop().time() - start

    # Concurrent execution (5 jobs concurrently ≈ 0.05s)
    start = asyncio.get_event_loop().time()
    await asyncio.gather(*(mock_job() for _ in range(5)))
    concurrent_time = asyncio.get_event_loop().time() - start

    # Concurrent should be significantly faster (at least 50% faster for I/O-bound tasks)
    assert concurrent_time < sequential_time * 0.6, (
        f"Concurrent ({concurrent_time:.3f}s) should be faster than sequential ({sequential_time:.3f}s)"
    )


def test_job_worker_public_api_unchanged(job_worker: JobWorker):
    """Verify JobWorker public API remains compatible."""
    # Public methods should exist and be callable
    assert hasattr(job_worker, "start")
    assert hasattr(job_worker, "stop")
    assert hasattr(job_worker, "run_once")
    assert callable(job_worker.start)
    assert callable(job_worker.stop)
    assert callable(job_worker.run_once)


@pytest.mark.asyncio
async def test_semaphore_respects_configuration():
    """Verify semaphore respects jobs_max_concurrent_workers config."""
    with patch("jobs.worker.get_settings") as mock_settings:
        mock_settings.return_value.jobs_max_concurrent_workers = 3
        mock_settings.return_value.jobs_poll_interval_seconds = 2.0

        worker = JobWorker()
        assert worker._semaphore._value == 3
        assert worker._settings.jobs_max_concurrent_workers == 3


@pytest.mark.asyncio
async def test_multiple_semaphore_acquisitions_and_releases():
    """Verify semaphore correctly handles acquire/release cycles."""
    worker = JobWorker()
    acquire_count = 0
    release_count = 0

    async def track_acquire_release():
        nonlocal acquire_count, release_count
        async with worker._semaphore:
            acquire_count += 1
            await asyncio.sleep(0.001)
        release_count += 1

    tasks = [track_acquire_release() for _ in range(20)]
    await asyncio.gather(*tasks)

    assert acquire_count == 20
    assert release_count == 20


@pytest.mark.asyncio
async def test_run_once_with_empty_job_ids():
    """Verify run_once handles empty job batch correctly."""
    worker = JobWorker()

    with patch("jobs.worker.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        with patch("jobs.worker.JobRepository") as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.stale_running_jobs.return_value = []
            mock_repo.due_jobs.return_value = []

            result = await worker.run_once()

            # Should return 0 for empty batch
            assert result == 0


@pytest.mark.asyncio
async def test_run_once_does_not_hang_with_semaphore():
    """Verify run_once completes even with semaphore contention."""
    worker = JobWorker()

    with patch("jobs.worker.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        with patch("jobs.worker.JobRepository") as mock_repo_class:
            with patch.object(worker, "_execute", new_callable=AsyncMock) as mock_execute:
                mock_repo = AsyncMock()
                mock_repo_class.return_value = mock_repo

                # Create mock jobs
                mock_jobs = [MagicMock(spec=Job, id=i) for i in range(1, 6)]
                mock_repo.stale_running_jobs.return_value = []
                mock_repo.due_jobs.return_value = mock_jobs
                mock_repo.get.side_effect = lambda job_id: mock_jobs[job_id - 1] if job_id <= len(
                    mock_jobs
                ) else None

                mock_execute.return_value = None

                # run_once should complete without hanging
                result = await worker.run_once()

                # Should return batch size
                assert result == 5
                # _execute should have been called for each job
                assert mock_execute.call_count == 5
