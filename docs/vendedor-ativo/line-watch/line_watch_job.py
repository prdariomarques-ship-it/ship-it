"""Job `lines.watch`: vigia das linhas do WhatsApp, autorreagendavel (mesmo padrao de `observation/scheduler.py` e `jobs/style_job.py`).

Cada rodada consulta o Evolution, decide os avisos (`services/line_watch.py`), enfileira `whatsapp.send_text` para o dono por uma linha
no ar e se reagenda. A rodada NUNCA deixa a corrente morrer: qualquer erro vira log e o proximo job e criado mesmo assim.
Desligado por padrao (`LINE_WATCH_ENABLED=false`): a semente `start` nem cria a corrente.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from jobs.registry import job_handler
from jobs.service import JobService
from repositories.job import JobRepository
from services import line_watch
from services.audit import record_log
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)
JOB_NAME = "lines.watch"


async def _run_round(db: AsyncSession, settings, jobs: JobService) -> None:
    instances = line_watch.watched_instances(settings)
    if not instances:
        return
    states = await line_watch.fetch_states(instances, base_url=settings.evolution_base_url, api_key=settings.evolution_api_key)
    events = await line_watch.evaluate(states, confirm_checks=settings.line_watch_confirm_checks,
                                       repeat_minutes=settings.line_watch_repeat_minutes)
    phone = settings.line_watch_alert_phone or settings.whatsapp_owner_alert_phone
    for event in events:
        text = line_watch.message_for(event, settings.line_watch_interval_seconds)
        sender = line_watch.pick_sender(states, event.instance, settings.evolution_personal_instance)
        sent = bool(phone and sender)
        await record_log(
            db, source="line_watch", level="info" if event.kind == "recovered" else "error",
            message=text, payload={"instance": event.instance, "state": event.state, "kind": event.kind,
                                   "sent_via": sender if sent else None, "no_phone": not phone, "no_open_line": sender is None},
        )
        if sent:
            await jobs.enqueue("whatsapp.send_text", {"to": phone, "content": text, "instance": sender})


@job_handler(JOB_NAME)
async def line_watch_tick(db: AsyncSession, payload: dict) -> None:
    settings = get_settings()
    jobs = JobService(db)
    try:
        await _run_round(db, settings, jobs)
    except Exception:  # noqa: BLE001 - a corrente nao pode morrer por um erro numa rodada
        logger.exception("line_watch: erro na rodada; segue para a proxima")
    await jobs.enqueue(JOB_NAME, delay_seconds=settings.line_watch_interval_seconds)


async def start(db: AsyncSession) -> None:
    """Semeia a primeira rodada. Idempotente: nao cria uma segunda corrente."""
    if not get_settings().line_watch_enabled:
        return
    if await JobRepository(db).pending_by_name(JOB_NAME) is not None:
        return
    await JobService(db).enqueue(JOB_NAME, delay_seconds=0)
