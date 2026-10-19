"""Suspension of automatic outbound WhatsApp (global and per Evolution instance).

Built on the existing runtime-settings mechanism (`services/app_settings.py`):
two editable entries are persisted in `app_settings`, layered over the
`Settings` singleton, and re-applied at startup -- no parallel config system.

Enforcement lives at the ONE place every automatic send converges on, the
`whatsapp.send_text` job handler (`jobs/handlers.py::send_whatsapp_text`), so a
message queued before the suspension is withheld as well. A withheld job
completes (it is NOT retried): after a suspension, stale replies must never be
released later in a burst. The suspension is checked before any reservation or
fence is taken, so it leaves nothing stuck in `needs_review`.

What a suspension does NOT touch (by design):
  - owner alerts (`_twin_alert_dedup_key` from the loop guard / risk gate, and
    `owner_alert` from the line watch): the owner must still learn about the
    incident that caused the suspension;
  - human sends made from the dashboard (`/api/whatsapp/send-*` call the
    provider directly and never pass through the queue handler).
"""
import re

from sqlalchemy.ext.asyncio import AsyncSession

from services.app_settings import update_setting
from services.audit import record_log
from utils.config import Settings

INSTANCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
KEY_GLOBAL = "automation_suspended"
KEY_INSTANCES = "automation_suspended_instances"
MIN_REASON_CHARS = 3
MAX_REASON_CHARS = 500


class InvalidSuspensionRequest(ValueError):
    pass


def parse_instances(raw: str | None) -> list[str]:
    """Comma-separated names -> sorted unique list. Invalid tokens are dropped, never guessed."""
    names = {token.strip() for token in (raw or "").split(",")}
    return sorted(name for name in names if INSTANCE_RE.fullmatch(name))


def suspension_reason(settings: Settings, instance: str | None) -> str | None:
    """Why automatic sends are suspended for `instance` right now, or None.

    Pure and cheap: it only reads the live (persisted-override-aware) settings.
    """
    if settings.automation_suspended:
        return "global"
    if instance and instance in parse_instances(settings.automation_suspended_instances):
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


def state(settings: Settings) -> dict:
    return {
        "global_suspended": bool(settings.automation_suspended),
        "suspended_instances": parse_instances(settings.automation_suspended_instances),
    }


async def set_global(db: AsyncSession, suspended: bool, actor_id: int | None, reason: str | None) -> dict:
    from utils.config import get_settings

    text = _validated_reason(reason)
    await update_setting(db, KEY_GLOBAL, suspended, actor_id)
    await record_log(
        db,
        source="automation_suspension",
        level="warning" if suspended else "info",
        message=f"Automação {'SUSPENSA' if suspended else 'retomada'} (global)",
        payload={"scope": "global", "suspended": suspended, "actor_id": actor_id, "reason": text},
    )
    return state(get_settings())


async def set_instance(
    db: AsyncSession, instance: str, suspended: bool, actor_id: int | None, reason: str | None
) -> dict:
    from utils.config import get_settings

    if not INSTANCE_RE.fullmatch(instance or ""):
        raise InvalidSuspensionRequest("Nome de instância inválido.")
    text = _validated_reason(reason)
    current = set(parse_instances(get_settings().automation_suspended_instances))
    if suspended:
        current.add(instance)
    else:
        current.discard(instance)
    await update_setting(db, KEY_INSTANCES, ",".join(sorted(current)), actor_id)
    await record_log(
        db,
        source="automation_suspension",
        level="warning" if suspended else "info",
        message=f"Automação {'SUSPENSA' if suspended else 'retomada'} na instância {instance}",
        payload={
            "scope": "instance", "instance": instance, "suspended": suspended,
            "actor_id": actor_id, "reason": text,
        },
    )
    return state(get_settings())
