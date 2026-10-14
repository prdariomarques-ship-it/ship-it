"""Job `darius.distill_style`: aprendizado do estilo do dono, autorreagendavel.

Mesmo padrao de `observation/scheduler.py`: a fila duravel (`jobs/`) e o agendador. Cada rodada processa um lote de mensagens
(`services/style_distill.py`), guarda o ultimo id visto no payload do PROXIMO job e se reagenda. Cursor no payload = reinicio
seguro, sem coluna nova. Desligado por padrao (`STYLE_DISTILL_ENABLED=false`): com a chave desligada o job nao processa nada, e a
semente `start` nem cria a corrente.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from jobs.registry import job_handler
from jobs.service import JobService
from repositories.job import JobRepository
from services.style_distill import distill_batch, record_distill_log
from utils.config import get_settings

JOB_NAME = "darius.distill_style"


@job_handler(JOB_NAME)
async def distill_style_tick(db: AsyncSession, payload: dict) -> None:
    settings = get_settings()
    after_id = int(payload.get("after_id") or 0)
    if settings.style_distill_enabled:
        stats = await distill_batch(db, after_id=after_id)
        after_id = stats.last_id
        if stats.scanned:
            await record_distill_log(db, stats)
    # Lote cheio = ainda ha mensagens novas: volta logo; senao espera o intervalo normal.
    full_batch = settings.style_distill_enabled and stats.scanned >= settings.style_distill_batch_size
    await JobService(db).enqueue(
        JOB_NAME,
        payload={"after_id": after_id},
        delay_seconds=0 if full_batch else settings.style_distill_interval_seconds,
    )


async def start(db: AsyncSession) -> None:
    """Semeia a primeira rodada. Idempotente: nao cria uma segunda corrente."""
    if not get_settings().style_distill_enabled:
        return
    if await JobRepository(db).pending_by_name(JOB_NAME) is not None:
        return
    await JobService(db).enqueue(JOB_NAME, payload={"after_id": 0}, delay_seconds=0)
