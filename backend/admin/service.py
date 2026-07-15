"""Read-only helpers backing the admin dashboard endpoints.

Everything here only *reads* — process metadata, existing DB tables, the
existing Prometheus registry, the existing `MemoryService.client` property,
the existing `WhatsAppProvider.health_check()`. Nothing here writes to a
model, calls an Orchestrator/Agent/Provider method that changes state, or
adds a new instrumentation point. See docs/DASHBOARD.md for the exact data
sources behind each field, including the ones that are honestly `None`
because no historical record exists yet.

Fields that must NEVER appear in any function's return value:
`encrypted_refresh_token`, `hashed_password`, any `*api_key*`,
`*_secret`, `access_token`, JWT strings.
"""
import subprocess
import time
from datetime import datetime

from prometheus_client import REGISTRY
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.schemas import ComponentStatus
from database.session import engine
from models.embedding import Embedding
from models.gdrive_indexed_file import GoogleDriveIndexedFile
from models.log import LogEntry
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

_PROCESS_STARTED_MONOTONIC = time.monotonic()


def uptime_seconds() -> float:
    return time.monotonic() - _PROCESS_STARTED_MONOTONIC


def _run_git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=3, check=True,
        )
        value = result.stdout.strip()
        return value or None
    except Exception:  # noqa: BLE001 - no .git in a production image is expected, not an error
        return None


def git_info() -> dict:
    """Best-effort repo metadata. Every field is `None` when unavailable
    (e.g. a production image built without the `.git` directory) — never
    fabricated."""
    return {
        "commit": _run_git("rev-parse", "--short", "HEAD"),
        "branch": _run_git("rev-parse", "--abbrev-ref", "HEAD"),
        "tag": _run_git("describe", "--tags", "--exact-match"),
    }


def system_resources() -> dict:
    """CPU/RAM/disk via psutil. Returns all-`None` if psutil is unavailable
    for some reason rather than raising — a resource widget failing must
    never take the rest of the dashboard down with it."""
    try:
        import psutil

        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_used_mb": round(memory.used / (1024 * 1024), 1),
            "memory_total_mb": round(memory.total / (1024 * 1024), 1),
            "memory_percent": memory.percent,
            "disk_used_gb": round(disk.used / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "disk_percent": disk.percent,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("System resource collection failed: %s", exc)
        return {
            "cpu_percent": None,
            "memory_used_mb": None,
            "memory_total_mb": None,
            "memory_percent": None,
            "disk_used_gb": None,
            "disk_total_gb": None,
            "disk_percent": None,
        }


def db_pool_info() -> dict:
    pool = engine.pool
    try:
        return {
            "db_pool_size": pool.size(),  # type: ignore[attr-defined]
            "db_pool_checked_out": pool.checkedout(),  # type: ignore[attr-defined]
        }
    except AttributeError:
        # NullPool (used for SQLite/tests) exposes neither method.
        return {"db_pool_size": None, "db_pool_checked_out": None}


def prometheus_snapshot(prefix: str = "darioos_") -> dict[str, list[dict]]:
    """JSON-serializable snapshot of every sample currently held by the
    existing Prometheus registry (`observability/metrics.py`), filtered to
    this app's own metrics. These are cumulative counters/histogram buckets,
    not per-minute rates — the frontend derives a rate by diffing two polls
    (see docs/DASHBOARD.md "Gráficos em tempo real")."""
    snapshot: dict[str, list[dict]] = {}
    for metric in REGISTRY.collect():
        if not metric.name.startswith(prefix):
            continue
        samples = [
            {"name": sample.name, "labels": sample.labels, "value": sample.value}
            for sample in metric.samples
        ]
        if samples:
            snapshot[metric.name] = samples
    return snapshot


def _metric_value(snapshot: dict[str, list[dict]], sample_name: str, **label_filter: str) -> float:
    """Sum every sample named exactly `sample_name` (e.g.
    "darioos_agent_runs_total" or "darioos_agent_run_duration_seconds_sum")
    across every label combination that matches `label_filter`.

    `prometheus_snapshot()` groups samples by Prometheus's *base* metric
    name (e.g. "darioos_agent_runs", without the "_total" suffix a Counter
    or Histogram adds to its individual samples) — the outer dict key is
    NOT the same string as a Counter's own `_total` sample name or a
    Histogram's `_sum`/`_count`/`_bucket` sample names. Searching by exact
    sample name across every group, instead of using `sample_name` as the
    dict key, is what makes this correct regardless of that grouping."""
    total = 0.0
    for samples in snapshot.values():
        for sample in samples:
            if sample["name"] != sample_name:
                continue
            if all(sample["labels"].get(key) == value for key, value in label_filter.items()):
                total += sample["value"]
    return total


def agent_run_stats(snapshot: dict[str, list[dict]], agent_name: str) -> dict:
    ok = _metric_value(snapshot, "darioos_agent_runs_total", agent=agent_name, status="ok")
    error = _metric_value(snapshot, "darioos_agent_runs_total", agent=agent_name, status="error")
    duration_sum = _metric_value(snapshot, "darioos_agent_run_duration_seconds_sum", agent=agent_name)
    duration_count = _metric_value(snapshot, "darioos_agent_run_duration_seconds_count", agent=agent_name)
    total = ok + error
    return {
        "runs_total": int(total) if snapshot else None,
        "runs_ok": int(ok) if snapshot else None,
        "runs_error": int(error) if snapshot else None,
        "avg_duration_seconds": round(duration_sum / duration_count, 3) if duration_count else None,
    }


def tool_call_stats(snapshot: dict[str, list[dict]], tool_name: str) -> dict:
    ok = _metric_value(snapshot, "darioos_agent_tool_calls_total", tool=tool_name, status="ok")
    error = _metric_value(snapshot, "darioos_agent_tool_calls_total", tool=tool_name, status="error")
    return {
        "calls_total": int(ok + error) if snapshot else None,
        "calls_ok": int(ok) if snapshot else None,
        "calls_error": int(error) if snapshot else None,
    }


async def _timed_check(coro) -> tuple[bool, float, str]:
    started = time.perf_counter()
    try:
        await coro
        return True, (time.perf_counter() - started) * 1000, "ok"
    except Exception as exc:  # noqa: BLE001 - report, never raise, from a status probe
        return False, (time.perf_counter() - started) * 1000, f"{type(exc).__name__}: {exc}"


async def check_database(db: AsyncSession) -> ComponentStatus:
    from sqlalchemy import text

    online, latency, detail = await _timed_check(db.execute(text("SELECT 1")))
    return ComponentStatus(name="database", online=online, detail=detail, latency_ms=round(latency, 1))


async def check_redis() -> ComponentStatus:
    from redis import asyncio as aioredis

    async def _ping():
        client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            await client.ping()
        finally:
            await client.aclose()

    online, latency, detail = await _timed_check(_ping())
    return ComponentStatus(name="redis", online=online, detail=detail, latency_ms=round(latency, 1))


async def check_qdrant() -> ComponentStatus:
    from memory.service import memory_service

    online, latency, detail = await _timed_check(memory_service.client.get_collections())
    return ComponentStatus(name="qdrant", online=online, detail=detail, latency_ms=round(latency, 1))


async def check_whatsapp() -> ComponentStatus:
    from providers.whatsapp.factory import get_whatsapp_provider

    provider = get_whatsapp_provider()
    started = time.perf_counter()
    try:
        healthy = await provider.health_check()
        latency = (time.perf_counter() - started) * 1000
        return ComponentStatus(
            name="whatsapp", online=healthy, detail=f"provider={provider.name}", latency_ms=round(latency, 1)
        )
    except Exception as exc:  # noqa: BLE001
        latency = (time.perf_counter() - started) * 1000
        return ComponentStatus(
            name="whatsapp", online=False, detail=f"{type(exc).__name__}: {exc}", latency_ms=round(latency, 1)
        )


def check_event_bus() -> ComponentStatus:
    from events.bus import event_bus

    handler_count = sum(len(v) for v in event_bus._handlers.values()) + sum(
        len(v) for v in event_bus._wildcard_handlers.values()
    )
    detail = f"{handler_count} handler(s) registered, redis_fanout={'ok' if event_bus._redis_available else 'degraded'}"
    return ComponentStatus(name="event_bus", online=True, detail=detail, latency_ms=None)


async def embeddings_by_source(db: AsyncSession) -> dict[str, int]:
    statement = select(Embedding.source, func.count()).group_by(Embedding.source)
    rows = (await db.execute(statement)).all()
    return {source: count for source, count in rows}


async def drive_index_stats(db: AsyncSession) -> tuple[int, datetime | None]:
    statement = select(func.count(), func.max(GoogleDriveIndexedFile.indexed_at))
    count, last_indexed = (await db.execute(statement)).one()
    return count, last_indexed


async def recent_log_for_source(db: AsyncSession, source_prefix: str) -> LogEntry | None:
    statement = (
        select(LogEntry)
        .where(LogEntry.source.like(f"{source_prefix}%"))
        .order_by(LogEntry.id.desc())
        .limit(1)
    )
    return (await db.execute(statement)).scalar_one_or_none()
