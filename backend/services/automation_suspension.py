"""Suspension of automatic outbound WhatsApp (global and per Evolution instance).

State lives in the `automation_suspensions` table (one row per scope, primary
key = scope), so suspend/resume are single-row INSERT/DELETE statements:
atomic, persistent across restarts, and visible to every process reading the
database. This replaces the earlier comma-separated `app_settings` value, whose
read-modify-write could lose a concurrent edit of another instance.

Enforcement lives at the ONE place every automatic send converges on, the
`whatsapp.send_text` job handler (`jobs/handlers.py::send_whatsapp_text`), so a
message queued before the suspension is withheld as well. A withheld job
completes (it is NOT retried): after a suspension, stale replies must never be
released later in a burst. The suspension is checked before any reservation or
fence is taken, so it leaves nothing stuck in `needs_review`.

Explicit behaviour of the edit API:
  - invalid input (bad name, reason outside 3..500 chars)  -> InvalidSuspensionRequest (HTTP 422);
  - suspending an instance that is not configured          -> UnknownInstance (HTTP 404). The name
    is matched case-insensitively and stored in its configured spelling;
  - resuming an instance that is not configured            -> allowed (cleans a stale row), idempotent;
  - repeating an edit (suspend a suspended scope, resume an active one) -> no error, `changed=False`;
  - concurrent edits of different scopes never interfere; the same scope converges.

What a suspension does NOT touch (by design):
  - owner alerts (`_twin_alert_dedup_key` from the loop guard / risk gate, and
    `owner_alert` from the line watch): the owner must still learn about the
    incident that caused the suspension;
  - human sends made from the dashboard (`/api/whatsapp/send-*` call the
    provider directly and never pass through the queue handler).

`Settings.automation_suspended` (env `AUTOMATION_SUSPENDED=true`) remains as a
static, restart-time kill switch that needs no database.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from models.automation_suspension import SCOPE_GLOBAL, SCOPE_INSTANCE_PREFIX, instance_scope
from repositories.automation_suspension import AutomationSuspensionRepository
from services.audit import record_log
from utils.config import Settings

INSTANCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
MIN_REASON_CHARS = 3
MAX_REASON_CHARS = 500
# Instances the backend addresses by name without a dedicated setting (see
# `process_inbound_whatsapp_message`'s extra agents).
BUILTIN_AGENT_INSTANCES = ("b2b-sales", "azusa-church")


class InvalidSuspensionRequest(ValueError):
    pass


class UnknownInstance(LookupError):
    pass


@dataclass(frozen=True)
class Change:
    state: dict
    changed: bool


def _csv(raw: str | None) -> list[str]:
    return [token.strip() for token in (raw or "").split(",") if token.strip()]


def configured_instances(settings: Settings) -> list[str]:
    """Every Evolution instance name this backend is configured to know, sorted and unique."""
    names = {
        settings.evolution_instance,
        settings.evolution_personal_instance,
        *_csv(settings.line_watch_instances),
        *_csv(settings.evolution_media_extra_instances),
        *BUILTIN_AGENT_INSTANCES,
    }
    return sorted(name for name in names if name and INSTANCE_RE.fullmatch(name))


def canonical_instance(settings: Settings, instance: str) -> str:
    """The configured spelling of `instance` (case-insensitive match), or raise."""
    if not INSTANCE_RE.fullmatch(instance or ""):
        raise InvalidSuspensionRequest("Nome de instância inválido.")
    for name in configured_instances(settings):
        if name.lower() == instance.lower():
            return name
    raise UnknownInstance(f"Instância não configurada: {instance}")


async def suspension_reason(db: AsyncSession, settings: Settings, instance: str | None) -> str | None:
    """Why automatic sends are suspended for `instance` right now, or None.

    Reads the database on every call (one indexed query), so a change made by
    any process or after a restart is honoured immediately.
    """
    if settings.automation_suspended:
        return "global"
    scopes = [SCOPE_GLOBAL] + ([instance_scope(instance)] if instance else [])
    active = await AutomationSuspensionRepository(db).scopes_in(scopes)
    if SCOPE_GLOBAL in active:
        return "global"
    if active:
        return f"instance:{instance}"
    return None


def is_protected_from_suspension(payload: dict) -> bool:
    """True for owner alerts, which must still be delivered during a suspension."""
    return bool(payload.get("owner_alert") or payload.get("_twin_alert_dedup_key"))


def _validated_reason(reason: str | None) -> str:
    text = (reason or "").strip()
    if len(text) < MIN_REASON_CHARS or len(text) > MAX_REASON_CHARS:
        raise InvalidSuspensionRequest(
            f"Informe o motivo ({MIN_REASON_CHARS} a {MAX_REASON_CHARS} caracteres)."
        )
    return text


def _utc_iso(value: datetime | None) -> str | None:
    # Stored as UTC; SQLite returns it naive and the browser would read it as local time. PostgreSQL returns it aware.
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


async def state(db: AsyncSession, settings: Settings) -> dict:
    rows = await AutomationSuspensionRepository(db).list_all()
    by_scope = {row.scope: row for row in rows}
    instances = sorted(
        scope[len(SCOPE_INSTANCE_PREFIX):] for scope in by_scope if scope.startswith(SCOPE_INSTANCE_PREFIX)
    )
    glob = by_scope.get(SCOPE_GLOBAL)
    return {
        "global_suspended": bool(settings.automation_suspended or glob),
        "global_forced_by_environment": bool(settings.automation_suspended),
        "suspended_instances": instances,
        "configured_instances": configured_instances(settings),
        "details": [
            {
                "scope": row.scope,
                "reason": row.reason,
                "actor_id": row.actor_id,
                "since": _utc_iso(row.created_at),
            }
            for row in rows
        ],
    }


async def _apply(
    db: AsyncSession, scope: str, suspended: bool, actor_id: int | None, reason: str, label: str
) -> bool:
    repo = AutomationSuspensionRepository(db)
    changed = await repo.suspend(scope, reason, actor_id) if suspended else await repo.resume(scope)
    await record_log(
        db,
        source="automation_suspension",
        level="warning" if suspended else "info",
        message=f"Automação {'SUSPENSA' if suspended else 'retomada'} ({label})",
        payload={
            "scope": scope, "suspended": suspended, "changed": changed,
            "actor_id": actor_id, "reason": reason,
        },
    )
    return changed


async def set_global(
    db: AsyncSession, settings: Settings, suspended: bool, actor_id: int | None, reason: str | None
) -> Change:
    text = _validated_reason(reason)
    changed = await _apply(db, SCOPE_GLOBAL, suspended, actor_id, text, "global")
    return Change(await state(db, settings), changed)


async def set_instance(
    db: AsyncSession, settings: Settings, instance: str, suspended: bool, actor_id: int | None,
    reason: str | None,
) -> Change:
    if not INSTANCE_RE.fullmatch(instance or ""):
        raise InvalidSuspensionRequest("Nome de instância inválido.")
    text = _validated_reason(reason)
    if suspended:
        name = canonical_instance(settings, instance)  # unknown -> UnknownInstance
    else:
        try:
            name = canonical_instance(settings, instance)
        except UnknownInstance:
            name = instance  # allow cleaning up a stale row for an instance no longer configured
    changed = await _apply(db, instance_scope(name), suspended, actor_id, text, f"instância {name}")
    return Change(await state(db, settings), changed)
