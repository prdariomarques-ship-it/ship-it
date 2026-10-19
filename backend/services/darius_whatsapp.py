"""WhatsApp -> DARIUS task flow.

    inbound message (already validated + deduplicated by the webhook)
      -> guards (suspension, human pause, age, antiloop, opt-out)      [jobs/handlers.py]
      -> link row claimed (UNIQUE dedupe_key) -> DARIUS task created with Idempotency-Key = dedupe_key
      -> DARIUS owns planning, approval and execution (it is the canonical runtime)
      -> poll the result; only a COMPLETED task with a non-empty result produces a reply
      -> reply handed to the EXISTING `whatsapp.send_text` job, which keeps enforcing the
         automation suspension, the human-pause revision, output safety and the Evolution transport
      -> audit: every transition is a `record_log(source="darius_whatsapp")` + the link row.

Principles (see DARIO_OS_INTEGRATION_STATUS.md):
  * Opt-in per Evolution instance (`darius_whatsapp_enabled` + `darius_whatsapp_instances`); with the
    flag off the legacy local pipeline is untouched.
  * No simulated success: if DARIUS is not configured the link is `skipped`; if it fails or is
    rejected the link is `failed`/`cancelled`; if no result arrives inside the reply window the link
    `expired` and a late answer is NEVER sent. There is deliberately no silent fallback to the local
    pipeline for an instance routed to DARIUS (that would be a second, unaudited answerer).
  * Reliability lives in DARIUS (leases, fencing, idempotency). This module only (a) derives a stable
    Idempotency-Key, (b) retries the *creation* (safe because of that key) and (c) never replays a reply:
    the link is moved to `reply_queued` BEFORE the send job is enqueued, so a crash in between loses
    one reply (visible in the panel as reply_job_id = NULL) instead of duplicating it.
  * No conversation content is stored in the link or in the audit log (ids, sizes, hash only).
"""
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from database.base import utcnow
from jobs.service import JobService
from models.darius_whatsapp_task import (
    CANCELLED,
    EXPIRED,
    FAILED,
    REPLY_QUEUED,
    SKIPPED,
    SUBMITTED,
    SUBMITTING,
    DariusWhatsAppTask,
)
from repositories.contact import ContactRepository
from repositories.darius_whatsapp_task import DariusWhatsAppTaskRepository
from repositories.message import MessageRepository
from services.audit import record_log
from services.darius_client import (
    DariusClient,
    DariusError,
    DariusNotConfigured,
    DariusNotFound,
    DariusUnavailable,
    get_service_client,
)
from utils.config import Settings
from utils.logging import get_logger

logger = get_logger(__name__)

SOURCE = "darius_whatsapp"
SUBMIT_JOB = "darius.whatsapp.submit"
POLL_JOB = "darius.whatsapp.poll"
MAX_HISTORY = 50
DARIUS_DONE_PREFIX = "DONE:"
SUBMIT_BACKOFF_BASE_SECONDS = 2.0


@dataclass(frozen=True)
class Dispatch:
    outcome: str  # submitted | retry_scheduled | duplicate | skipped | failed
    link_id: int


def routed_instances(settings: Settings) -> set[str]:
    return {name.strip() for name in settings.darius_whatsapp_instances.split(",") if name.strip()}


def is_enabled_for(settings: Settings, instance: str | None) -> bool:
    return bool(settings.darius_whatsapp_enabled and instance and instance in routed_instances(settings))


def dedupe_key(instance: str, message) -> str:
    """Stable per (instance, provider message id); falls back to the local id for rows without one."""
    external = (getattr(message, "external_id", None) or "").strip() or f"local-{message.id}"
    digest = hashlib.sha256(f"{instance}\x1f{external}".encode()).hexdigest()
    return f"wa-{digest[:40]}"


def build_objective(settings: Settings, instance: str, contact_id: int, content: str) -> str:
    limit = max(200, settings.darius_whatsapp_max_objective_chars)
    text = content.strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + " [mensagem truncada]"
    return (
        f"Canal: WhatsApp (instância {instance}). Contato interno #{contact_id}.\n"
        f'Mensagem recebida: """{text}"""\n'
        "Tarefa: redigir a resposta que será enviada por WhatsApp a esse contato. "
        "Escreva em português do Brasil, sem explicações extras. "
        # DARIUS contract (src/core/engine.ts): a task completes only when the agent's act output starts with
        # "DONE:"; the text after the prefix becomes the task result, i.e. the exact message we will send.
        f"Quando terminar, responda EXATAMENTE neste formato: {DARIUS_DONE_PREFIX} <texto da mensagem a enviar>"
    )


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _note(row: DariusWhatsAppTask, kind: str, **extra) -> None:
    entry = {"at": utcnow().isoformat(), "kind": kind, **extra}
    row.history = [*(row.history or []), entry][-MAX_HISTORY:]


async def _log(db: AsyncSession, row: DariusWhatsAppTask, message: str, *, level: str = "info", **extra) -> None:
    await record_log(
        db, source=SOURCE, level=level, message=message,
        payload={
            "link_id": row.id, "message_id": row.message_id, "contact_id": row.contact_id,
            "instance": row.instance, "status": row.status, "darius_task_id": row.darius_task_id, **extra,
        },
    )


async def _finish(db: AsyncSession, row: DariusWhatsAppTask, status: str, reason: str, *, level: str = "info") -> None:
    row.status = status
    row.last_error = reason if status in (FAILED, SKIPPED, EXPIRED, CANCELLED) else row.last_error
    row.finished_at = utcnow()
    _note(row, status, reason=reason)
    await DariusWhatsAppTaskRepository(db).save(row)
    await _log(db, row, f"Fluxo DARIUS encerrado: {status} ({reason})", level=level, reason=reason)


async def dispatch_inbound(
    db: AsyncSession, settings: Settings, *, contact, message, instance: str,
    control_revision: int | None, client: DariusClient | None = None,
) -> Dispatch:
    """Claim the link for this message and create the DARIUS task. Idempotent per message."""
    repo = DariusWhatsAppTaskRepository(db)
    row, created = await repo.claim(
        dedupe_key=dedupe_key(instance, message), message_id=message.id, contact_id=contact.id,
        instance=instance, control_revision=control_revision,
    )
    if not created and row.status != SUBMITTING:
        await _log(db, row, "Mensagem já tratada pelo fluxo DARIUS (duplicata ignorada)")
        return Dispatch("duplicate", row.id)
    return await submit_link(db, settings, row, client=client, content=message.content)


async def submit_link(
    db: AsyncSession, settings: Settings, row: DariusWhatsAppTask, *,
    client: DariusClient | None = None, content: str | None = None,
) -> Dispatch:
    """Create (or re-create, idempotently) the DARIUS task for a link in SUBMITTING."""
    if content is None:
        message = await MessageRepository(db).get(row.message_id)
        if message is None:
            await _finish(db, row, FAILED, "message_missing", level="error")
            return Dispatch("failed", row.id)
        content = message.content
    objective = build_objective(settings, row.instance, row.contact_id, content)
    row.attempts += 1
    try:
        summary = await (client or get_service_client()).create_task(
            objective, idempotency_key=row.dedupe_key, completion="non_empty"
        )
    except DariusNotConfigured:
        await _finish(db, row, SKIPPED, "darius_not_configured", level="warning")
        return Dispatch("skipped", row.id)
    except DariusError as exc:
        transient = isinstance(exc, DariusUnavailable) or exc.outcome_unknown
        reason = f"{type(exc).__name__}:{exc.code or exc.status_code or 'n/a'}"
        if not transient:
            await _finish(db, row, FAILED, reason, level="error")
            return Dispatch("failed", row.id)
        if row.attempts >= max(1, settings.jobs_default_max_attempts):
            await _finish(db, row, FAILED, f"{reason}:attempts_exhausted", level="error")
            return Dispatch("failed", row.id)
        row.last_error = reason
        _note(row, "submit_retry", reason=reason, attempt=row.attempts)
        await DariusWhatsAppTaskRepository(db).save(row)
        delay = SUBMIT_BACKOFF_BASE_SECONDS * (2 ** (row.attempts - 1))
        await JobService(db).enqueue(SUBMIT_JOB, {"link_id": row.id}, delay_seconds=delay)
        await _log(db, row, "DARIUS indisponível ao criar a tarefa; nova tentativa agendada (mesma Idempotency-Key)",
                   level="warning", reason=reason, retry_in_seconds=delay)
        return Dispatch("retry_scheduled", row.id)
    row.darius_task_id = summary.id
    row.darius_status = summary.status
    row.status = SUBMITTED
    row.last_error = None
    _note(row, "submitted", darius_task_id=summary.id, darius_status=summary.status)
    await DariusWhatsAppTaskRepository(db).save(row)
    await JobService(db).enqueue(POLL_JOB, {"link_id": row.id}, delay_seconds=settings.darius_whatsapp_poll_seconds)
    await _log(db, row, "Tarefa DARIUS criada para a mensagem do WhatsApp", darius_status=summary.status)
    return Dispatch("submitted", row.id)


async def poll_link(
    db: AsyncSession, settings: Settings, row: DariusWhatsAppTask, *, client: DariusClient | None = None
) -> str:
    """One poll of a SUBMITTED link. Returns the resulting link status (unchanged if still waiting)."""
    if row.status != SUBMITTED or not row.darius_task_id:
        return row.status
    api = client or get_service_client()
    expired = utcnow() - _aware(row.created_at) > timedelta(seconds=settings.darius_whatsapp_reply_timeout_seconds)
    try:
        result = await api.get_result(row.darius_task_id)
    except DariusNotFound:
        await _finish(db, row, FAILED, "darius_task_not_found", level="error")
        return row.status
    except DariusNotConfigured:
        await _finish(db, row, FAILED, "darius_not_configured", level="error")
        return row.status
    except DariusUnavailable as exc:
        if expired:
            await _finish(db, row, EXPIRED, "reply_window_elapsed_darius_unreachable", level="warning")
            return row.status
        _note(row, "poll_unavailable", reason=type(exc).__name__)
        await DariusWhatsAppTaskRepository(db).save(row)
        await JobService(db).enqueue(POLL_JOB, {"link_id": row.id}, delay_seconds=settings.darius_whatsapp_poll_seconds)
        return row.status
    except DariusError as exc:
        await _finish(db, row, FAILED, f"{type(exc).__name__}:{exc.code or exc.status_code or 'n/a'}", level="error")
        return row.status

    if result.status != row.darius_status:
        row.darius_status = result.status
        _note(row, "darius_status", darius_status=result.status)
        await _log(db, row, f"Tarefa DARIUS agora {result.status}", darius_status=result.status)

    if result.status == "COMPLETED" and result.done:
        reply = (result.result or "").strip()
        if not reply:
            await _finish(db, row, FAILED, "empty_result", level="error")
            return row.status
        await _queue_reply(db, row, reply)
        return row.status
    if result.status == "FAILED":
        await _finish(db, row, FAILED, "darius_task_failed", level="error")
        return row.status
    if result.status == "CANCELLED":
        await _finish(db, row, CANCELLED, "darius_task_cancelled_or_rejected")
        return row.status
    if expired:
        try:
            await api.cancel(row.darius_task_id)  # best effort: do not leave a stale task consuming capacity
        except DariusError:
            pass
        await _finish(db, row, EXPIRED, "reply_window_elapsed", level="warning")
        return row.status
    await DariusWhatsAppTaskRepository(db).save(row)
    await JobService(db).enqueue(POLL_JOB, {"link_id": row.id}, delay_seconds=settings.darius_whatsapp_poll_seconds)
    return row.status


async def _queue_reply(db: AsyncSession, row: DariusWhatsAppTask, reply: str) -> None:
    contact = await ContactRepository(db).get(row.contact_id)
    if contact is None or not contact.phone:
        await _finish(db, row, FAILED, "contact_without_phone", level="error")
        return
    # At-most-once: persist the state change BEFORE enqueueing the send.
    row.status = REPLY_QUEUED
    row.reply_chars = len(reply)
    row.reply_sha256 = hashlib.sha256(reply.encode()).hexdigest()
    row.finished_at = utcnow()
    _note(row, "reply_queued", chars=len(reply))
    await DariusWhatsAppTaskRepository(db).save(row)
    payload: dict = {
        "to": contact.phone, "content": reply, "instance": row.instance, "darius_task_id": row.darius_task_id,
    }
    if row.control_revision is not None:
        payload["control_revision"] = row.control_revision  # a human pause/resume after submission blocks the send
    job = await JobService(db).enqueue("whatsapp.send_text", payload)
    row.reply_job_id = job.id
    await DariusWhatsAppTaskRepository(db).save(row)
    await _log(db, row, "Resposta do DARIUS entregue à fila de envio do WhatsApp", reply_chars=row.reply_chars,
               reply_job_id=job.id)
