"""Admin Dashboard API (Sprint 4): read-only, ADMIN-only, never leaks secrets."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from auth.jwt import create_access_token
from auth.password import hash_password
from models.email_account import EmailAccount
from models.embedding import Embedding
from models.gdrive_account import GoogleDriveAccount
from models.job import Job, JobStatus
from models.log import LogEntry
from models.message import Message, MessageDirection, MessageMediaType
from models.user import User, UserRole

ADMIN_ENDPOINTS = [
    "/api/admin",
    "/api/admin/status",
    "/api/admin/system",
    "/api/admin/agents",
    "/api/admin/tools",
    "/api/admin/logs",
    "/api/admin/google",
    "/api/admin/memory",
    "/api/admin/executions",
    "/api/admin/users",
    "/api/admin/metrics",
    "/api/admin/whatsapp",
]


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def admin_user(session_factory) -> User:
    async with session_factory() as session:
        user = User(
            email="admin@darioos.test",
            full_name="Admin",
            hashed_password=hash_password("supersecret1"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def regular_user(session_factory) -> User:
    async with session_factory() as session:
        user = User(
            email="user@darioos.test",
            full_name="User",
            hashed_password=hash_password("supersecret1"),
            role=UserRole.USER,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
def admin_headers(admin_user) -> dict[str, str]:
    token = create_access_token(str(admin_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_headers(regular_user) -> dict[str, str]:
    token = create_access_token(str(regular_user.id))
    return {"Authorization": f"Bearer {token}"}


# --- Access control -----------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
async def test_admin_endpoint_requires_authentication(client, endpoint):
    response = await client.get(endpoint)
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
async def test_admin_endpoint_rejects_non_admin(client, user_headers, endpoint):
    response = await client.get(endpoint, headers=user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
async def test_admin_endpoint_allows_admin(client, admin_headers, endpoint):
    response = await client.get(endpoint, headers=admin_headers)
    assert response.status_code == 200


# --- /admin (index) -------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_index_reflects_seeded_data(
    client, admin_headers, admin_user, regular_user
):
    response = await client.get("/api/admin", headers=admin_headers)
    body = response.json()
    assert body["users_total"] == 2
    assert body["agents_total"] > 0
    assert body["tools_total"] > 0
    assert isinstance(body["uptime_seconds"], float)


@pytest.mark.asyncio
async def test_admin_index_second_call_is_served_from_cache(client, admin_headers):
    first = await client.get("/api/admin", headers=admin_headers)
    second = await client.get("/api/admin", headers=admin_headers)
    assert first.json() == second.json()


# --- /admin/status ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_status_reports_every_expected_component(client, admin_headers):
    response = await client.get("/api/admin/status", headers=admin_headers)
    names = {item["name"] for item in response.json()}
    assert names == {
        "backend",
        "database",
        "redis",
        "qdrant",
        "whatsapp",
        "event_bus",
        "memory",
        "google_oauth",
    }


@pytest.mark.asyncio
async def test_admin_status_backend_is_always_online(client, admin_headers):
    response = await client.get("/api/admin/status", headers=admin_headers)
    backend = next(item for item in response.json() if item["name"] == "backend")
    assert backend["online"] is True
    assert backend["latency_ms"] == 0.0


# --- /admin/system ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_system_returns_version_and_uptime(client, admin_headers):
    response = await client.get("/api/admin/system", headers=admin_headers)
    body = response.json()
    assert body["app_name"] == "Dario OS"
    assert isinstance(body["uptime_seconds"], float)
    assert body["environment"] == "test"


@pytest.mark.asyncio
async def test_admin_system_exposes_provider_names_but_never_secrets(
    client, admin_headers
):
    response = await client.get("/api/admin/system", headers=admin_headers)
    body = response.json()
    assert body["whatsapp_provider"] == "openwa"
    assert body["mail_provider"] == "gmail"
    assert "api_key" not in response.text.lower()
    assert "secret" not in response.text.lower()


# --- /admin/agents ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_agents_lists_every_registered_agent_with_tool_counts(
    client, admin_headers
):
    from agents.registry import list_agents

    response = await client.get("/api/admin/agents", headers=admin_headers)
    body = response.json()
    assert {item["name"] for item in body} == {agent.name for agent in list_agents()}
    for item in body:
        assert item["tool_count"] >= 0
        assert (
            item["last_execution"] is None
        )  # no LogEntry seeded for any agent in this test


@pytest.mark.asyncio
async def test_admin_agents_reflects_real_prometheus_counters_end_to_end(
    client, admin_headers
):
    """Regression test: `agent_run_stats` must read the *actual* dict shape
    `prometheus_snapshot()` produces from the real Prometheus registry, not
    just a hand-built fixture — a prior version looked up the snapshot by
    the full suffixed sample name (e.g. "darioos_agent_runs_total") as the
    outer dict key, but `prometheus_snapshot()` groups by Prometheus's base
    metric name ("darioos_agent_runs"), so every stat silently stayed
    zero/null in production despite passing with a synthetic snapshot."""
    from observability.metrics import record_agent_run

    record_agent_run(
        agent="personal", provider="openai", status="ok", duration_seconds=2.0
    )
    record_agent_run(
        agent="personal", provider="openai", status="ok", duration_seconds=4.0
    )

    response = await client.get("/api/admin/agents", headers=admin_headers)
    personal = next(item for item in response.json() if item["name"] == "personal")
    assert personal["runs_total"] >= 2
    assert personal["runs_ok"] >= 2
    assert personal["avg_duration_seconds"] is not None
    assert personal["avg_duration_seconds"] > 0


# --- /admin/tools -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_tools_marks_unavailable_fields_as_null_not_fabricated(
    client, admin_headers
):
    from agents.tools.registry import list_tools

    response = await client.get("/api/admin/tools", headers=admin_headers)
    body = response.json()
    assert {item["name"] for item in body} == {tool.name for tool in list_tools()}
    for item in body:
        # Neither field has a real data source (see admin/service.py docstring) —
        # must stay null, never a fabricated/default value.
        assert item["permissions"] is None
        assert item["last_call"] is None
        assert isinstance(item["parameters"], dict)


@pytest.mark.asyncio
async def test_admin_tools_reflects_real_prometheus_counters_end_to_end(
    client, admin_headers
):
    """Same regression as test_admin_agents_reflects_real_prometheus_counters_end_to_end,
    for the Tool Registry side (`tool_call_stats`)."""
    from agents.tools.registry import list_tools
    from observability.metrics import record_tool_call

    any_tool_name = list_tools()[0].name
    record_tool_call(any_tool_name, "ok")
    record_tool_call(any_tool_name, "error")

    response = await client.get("/api/admin/tools", headers=admin_headers)
    tool = next(item for item in response.json() if item["name"] == any_tool_name)
    assert tool["calls_total"] >= 2
    assert tool["calls_ok"] >= 1
    assert tool["calls_error"] >= 1


# --- /admin/logs ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_logs_filters_by_level_and_search(
    client, admin_headers, session_factory
):
    async with session_factory() as session:
        session.add_all(
            [
                LogEntry(
                    level="error", source="agent:assistant", message="boom", payload={}
                ),
                LogEntry(
                    level="info", source="webhook", message="all good", payload={}
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/api/admin/logs", headers=admin_headers, params={"level": "error"}
    )
    body = response.json()
    assert len(body) == 1
    assert body[0]["message"] == "boom"

    response = await client.get(
        "/api/admin/logs", headers=admin_headers, params={"search": "good"}
    )
    body = response.json()
    assert len(body) == 1
    assert body[0]["source"] == "webhook"

    response = await client.get(
        "/api/admin/logs", headers=admin_headers, params={"source": "webhook"}
    )
    body = response.json()
    assert len(body) == 1
    assert body[0]["source"] == "webhook"


# --- /admin/google ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_google_never_leaks_the_encrypted_refresh_token(
    client, admin_headers, admin_user, session_factory
):
    async with session_factory() as session:
        session.add(
            EmailAccount(
                user_id=admin_user.id,
                provider="google",
                email_address="dario@gmail.com",
                encrypted_refresh_token="super-secret-token-value",
                scopes=["gmail.readonly"],
                connected_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    response = await client.get("/api/admin/google", headers=admin_headers)
    assert "super-secret-token-value" not in response.text
    assert "encrypted_refresh_token" not in response.text
    body = response.json()
    assert body["mail"]["connected_accounts"] == 1
    assert body["mail"]["accounts"][0]["label"] == "dario@gmail.com"
    assert body["calendar"]["connected_accounts"] == 0


@pytest.mark.asyncio
async def test_admin_google_drive_reports_indexed_file_stats(
    client, admin_headers, admin_user, session_factory
):
    async with session_factory() as session:
        session.add(
            GoogleDriveAccount(
                user_id=admin_user.id,
                provider="google",
                account_label="dario@gmail.com",
                encrypted_refresh_token="another-secret",
                scopes=["drive.readonly"],
                connected_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    response = await client.get("/api/admin/google", headers=admin_headers)
    body = response.json()
    assert body["drive"]["connected_accounts"] == 1
    assert body["drive"]["indexed_items"] == 0
    assert "another-secret" not in response.text


# --- /admin/memory ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_memory_counts_embeddings_by_source(
    client, admin_headers, session_factory
):
    async with session_factory() as session:
        session.add_all(
            [
                Embedding(source="whatsapp", content="a", vector_id="v1"),
                Embedding(source="whatsapp", content="b", vector_id="v2"),
                Embedding(source="knowledge", content="c", vector_id="v3"),
            ]
        )
        await session.commit()

    response = await client.get("/api/admin/memory", headers=admin_headers)
    body = response.json()
    assert body["embeddings_total"] == 3
    assert body["embeddings_by_source"] == {"whatsapp": 2, "knowledge": 1}
    assert body["cache_backend"] in ("redis", "in-memory (fallback)")


# --- /admin/executions ------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_executions_merges_jobs_and_agent_logs(
    client, admin_headers, session_factory
):
    async with session_factory() as session:
        session.add(
            Job(name="whatsapp.process_inbound", status=JobStatus.SUCCEEDED, payload={})
        )
        session.add(
            LogEntry(level="info", source="agent:personal", message="ran", payload={})
        )
        session.add(
            LogEntry(
                level="info", source="webhook", message="not an agent log", payload={}
            )
        )
        await session.commit()

    response = await client.get(
        "/api/admin/executions", headers=admin_headers, params={"period": "24h"}
    )
    body = response.json()
    kinds = {entry["kind"] for entry in body}
    assert kinds == {"job", "log"}
    names = {entry["name"] for entry in body}
    assert (
        "webhook" not in names
    )  # only agent:* logs are surfaced, not every log source


@pytest.mark.asyncio
async def test_admin_executions_filters_by_agent(
    client, admin_headers, session_factory
):
    async with session_factory() as session:
        session.add(
            Job(name="whatsapp.process_inbound", status=JobStatus.SUCCEEDED, payload={})
        )
        session.add(
            LogEntry(level="info", source="agent:personal", message="ran", payload={})
        )
        session.add(
            LogEntry(
                level="info", source="agent:assistant", message="also ran", payload={}
            )
        )
        await session.commit()

    response = await client.get(
        "/api/admin/executions",
        headers=admin_headers,
        params={"period": "24h", "agent": "personal"},
    )
    body = response.json()
    assert all(entry["kind"] != "log" or entry["agent"] == "personal" for entry in body)


@pytest.mark.asyncio
async def test_admin_executions_rejects_invalid_period(client, admin_headers):
    response = await client.get(
        "/api/admin/executions", headers=admin_headers, params={"period": "invalid"}
    )
    assert response.status_code == 422


# --- /admin/users -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_users_never_leaks_password_hash(
    client, admin_headers, admin_user, regular_user
):
    response = await client.get("/api/admin/users", headers=admin_headers)
    assert "hashed_password" not in response.text
    body = response.json()
    assert {item["email"] for item in body} == {
        "admin@darioos.test",
        "user@darioos.test",
    }


# --- /admin/metrics ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_metrics_returns_a_timestamped_snapshot(client, admin_headers):
    response = await client.get("/api/admin/metrics", headers=admin_headers)
    body = response.json()
    assert "timestamp" in body
    assert isinstance(body["metrics"], dict)


# --- /admin/whatsapp --------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_whatsapp_counts_messages_by_direction(
    client, admin_headers, session_factory
):
    from models.contact import Contact

    async with session_factory() as session:
        contact = Contact(name="Test Contact", phone="5511999990000")
        session.add(contact)
        await session.flush()
        session.add_all(
            [
                Message(
                    contact_id=contact.id,
                    direction=MessageDirection.OUTBOUND,
                    media_type=MessageMediaType.TEXT,
                    content="oi",
                ),
                Message(
                    contact_id=contact.id,
                    direction=MessageDirection.INBOUND,
                    media_type=MessageMediaType.TEXT,
                    content="oi de volta",
                ),
                Message(
                    contact_id=contact.id,
                    direction=MessageDirection.INBOUND,
                    media_type=MessageMediaType.TEXT,
                    content="mais uma",
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/admin/whatsapp", headers=admin_headers)
    body = response.json()
    assert body["messages_sent"] == 1
    assert body["messages_received"] == 2
    assert "provider" in body


# --- admin/service.py unit tests (pure helpers, no HTTP round trip needed) --------
def test_metric_value_accumulates_only_matching_samples():
    from admin.service import _metric_value

    snapshot = {
        "darioos_agent_runs_total": [
            {
                "name": "darioos_agent_runs_total",
                "labels": {"agent": "personal", "status": "ok"},
                "value": 3.0,
            },
            {
                "name": "darioos_agent_runs_total",
                "labels": {"agent": "personal", "status": "error"},
                "value": 1.0,
            },
            {
                "name": "darioos_agent_runs_total",
                "labels": {"agent": "assistant", "status": "ok"},
                "value": 9.0,
            },
        ]
    }
    assert (
        _metric_value(
            snapshot, "darioos_agent_runs_total", agent="personal", status="ok"
        )
        == 3.0
    )


def test_agent_run_stats_computes_average_duration_from_histogram_sum_and_count():
    from admin.service import agent_run_stats

    snapshot = {
        "darioos_agent_runs_total": [
            {
                "name": "darioos_agent_runs_total",
                "labels": {"agent": "personal", "status": "ok"},
                "value": 4.0,
            },
        ],
        "darioos_agent_run_duration_seconds_sum": [
            {
                "name": "darioos_agent_run_duration_seconds_sum",
                "labels": {"agent": "personal"},
                "value": 8.0,
            },
        ],
        "darioos_agent_run_duration_seconds_count": [
            {
                "name": "darioos_agent_run_duration_seconds_count",
                "labels": {"agent": "personal"},
                "value": 4.0,
            },
        ],
    }
    stats = agent_run_stats(snapshot, "personal")
    assert stats["runs_ok"] == 4
    assert stats["avg_duration_seconds"] == 2.0


def test_tool_call_stats_counts_ok_and_error_separately():
    from admin.service import tool_call_stats

    snapshot = {
        "darioos_agent_tool_calls_total": [
            {
                "name": "darioos_agent_tool_calls_total",
                "labels": {"tool": "send_whatsapp_message", "status": "ok"},
                "value": 5.0,
            },
            {
                "name": "darioos_agent_tool_calls_total",
                "labels": {"tool": "send_whatsapp_message", "status": "error"},
                "value": 2.0,
            },
        ]
    }
    stats = tool_call_stats(snapshot, "send_whatsapp_message")
    assert stats == {"calls_total": 7, "calls_ok": 5, "calls_error": 2}


def test_system_resources_degrades_to_all_none_when_psutil_fails(monkeypatch):
    import psutil

    from admin.service import system_resources

    def _raise(*args, **kwargs):
        raise RuntimeError("no /proc on this platform")

    monkeypatch.setattr(psutil, "virtual_memory", _raise)
    result = system_resources()
    assert result == {
        "cpu_percent": None,
        "memory_used_mb": None,
        "memory_total_mb": None,
        "memory_percent": None,
        "disk_used_gb": None,
        "disk_total_gb": None,
        "disk_percent": None,
    }


@pytest.mark.asyncio
async def test_drive_index_stats_returns_zero_and_none_when_nothing_indexed(
    session_factory,
):
    from admin.service import drive_index_stats

    async with session_factory() as session:
        count, last_indexed = await drive_index_stats(session)
    assert count == 0
    assert last_indexed is None


# --- P6: Job Management Operations (cancel, retry) ---


@pytest.mark.asyncio
async def test_admin_cancel_job_queued_succeeds(client, admin_headers, session_factory):
    """Admin can cancel a QUEUED job."""
    async with session_factory() as session:
        job = Job(name="test.job", status=JobStatus.QUEUED, payload={})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    response = await client.post(
        f"/api/admin/jobs/{job_id}/cancel", headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == JobStatus.CANCELLED.value
    assert body["job_id"] == job_id

    async with session_factory() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        updated_job = result.scalar_one()
        assert updated_job.status == JobStatus.CANCELLED
        assert updated_job.finished_at is not None


@pytest.mark.asyncio
async def test_admin_cancel_job_running_succeeds(
    client, admin_headers, session_factory
):
    """Admin can cancel a RUNNING job."""
    async with session_factory() as session:
        job = Job(name="test.job", status=JobStatus.RUNNING, payload={})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    response = await client.post(
        f"/api/admin/jobs/{job_id}/cancel", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == JobStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_admin_cancel_job_succeeded_fails(client, admin_headers, session_factory):
    """Admin cannot cancel a SUCCEEDED job."""
    async with session_factory() as session:
        job = Job(name="test.job", status=JobStatus.SUCCEEDED, payload={})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    response = await client.post(
        f"/api/admin/jobs/{job_id}/cancel", headers=admin_headers
    )
    assert response.status_code == 400
    assert "cannot cancel" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_cancel_job_failed_fails(client, admin_headers, session_factory):
    """Admin cannot cancel a FAILED job."""
    async with session_factory() as session:
        job = Job(name="test.job", status=JobStatus.FAILED, payload={})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    response = await client.post(
        f"/api/admin/jobs/{job_id}/cancel", headers=admin_headers
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_cancel_nonexistent_job_returns_404(client, admin_headers):
    """Cancelling nonexistent job returns 404."""
    response = await client.post("/api/admin/jobs/99999/cancel", headers=admin_headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_retry_job_failed_succeeds(client, admin_headers, session_factory):
    """Admin can retry a FAILED job (resets attempts to 0, clears error)."""
    async with session_factory() as session:
        job = Job(
            name="test.job",
            status=JobStatus.FAILED,
            payload={},
            attempts=3,
            last_error="Something went wrong",
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    response = await client.post(
        f"/api/admin/jobs/{job_id}/retry", headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == JobStatus.QUEUED.value
    assert body["job_id"] == job_id

    async with session_factory() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        updated_job = result.scalar_one()
        assert updated_job.status == JobStatus.QUEUED
        assert updated_job.attempts == 0  # reset
        assert updated_job.last_error is None  # cleared


@pytest.mark.asyncio
async def test_admin_retry_job_cancelled_succeeds(
    client, admin_headers, session_factory
):
    """Admin can retry a CANCELLED job."""
    async with session_factory() as session:
        job = Job(name="test.job", status=JobStatus.CANCELLED, payload={})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    response = await client.post(
        f"/api/admin/jobs/{job_id}/retry", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == JobStatus.QUEUED.value


@pytest.mark.asyncio
async def test_admin_retry_job_succeeded_fails(client, admin_headers, session_factory):
    """Admin cannot retry a SUCCEEDED job."""
    async with session_factory() as session:
        job = Job(name="test.job", status=JobStatus.SUCCEEDED, payload={})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    response = await client.post(
        f"/api/admin/jobs/{job_id}/retry", headers=admin_headers
    )
    assert response.status_code == 400
    assert "cannot retry" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_retry_job_queued_fails(client, admin_headers, session_factory):
    """Admin cannot retry a QUEUED job (only FAILED or CANCELLED)."""
    async with session_factory() as session:
        job = Job(name="test.job", status=JobStatus.QUEUED, payload={})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    response = await client.post(
        f"/api/admin/jobs/{job_id}/retry", headers=admin_headers
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_retry_nonexistent_job_returns_404(client, admin_headers):
    """Retrying nonexistent job returns 404."""
    response = await client.post("/api/admin/jobs/99999/retry", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_cancel_job_creates_audit_log(
    client, admin_headers, session_factory
):
    """Cancelling a job creates an audit log entry."""
    async with session_factory() as session:
        job = Job(name="test.job", status=JobStatus.QUEUED, payload={})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    await client.post(f"/api/admin/jobs/{job_id}/cancel", headers=admin_headers)

    async with session_factory() as session:
        result = await session.execute(
            select(LogEntry)
            .where(LogEntry.source == "admin:job_cancel")
            .order_by(LogEntry.id.desc())
        )
        log = result.scalars().first()
        assert log is not None
        assert log.payload["job_id"] == job_id


@pytest.mark.asyncio
async def test_admin_retry_job_creates_audit_log(
    client, admin_headers, session_factory
):
    """Retrying a job creates an audit log entry."""
    async with session_factory() as session:
        job = Job(name="test.job", status=JobStatus.FAILED, payload={})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    await client.post(f"/api/admin/jobs/{job_id}/retry", headers=admin_headers)

    async with session_factory() as session:
        result = await session.execute(
            select(LogEntry)
            .where(LogEntry.source == "admin:job_retry")
            .order_by(LogEntry.id.desc())
        )
        log = result.scalars().first()
        assert log is not None
        assert log.payload["job_id"] == job_id


@pytest.mark.asyncio
async def test_admin_job_operations_require_authentication(client, session_factory):
    """Job management endpoints require authentication."""
    async with session_factory() as session:
        job = Job(name="test.job", status=JobStatus.QUEUED, payload={})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    response = await client.post(f"/api/admin/jobs/{job_id}/cancel")
    assert response.status_code == 401

    response = await client.post(f"/api/admin/jobs/{job_id}/retry")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_job_operations_require_admin_role(
    client, user_headers, session_factory
):
    """Job management endpoints require ADMIN role."""
    async with session_factory() as session:
        job = Job(name="test.job", status=JobStatus.QUEUED, payload={})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    response = await client.post(
        f"/api/admin/jobs/{job_id}/cancel", headers=user_headers
    )
    assert response.status_code == 403

    response = await client.post(
        f"/api/admin/jobs/{job_id}/retry", headers=user_headers
    )
    assert response.status_code == 403
