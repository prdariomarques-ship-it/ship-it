"""Job handlers of the WhatsApp -> DARIUS flow (see services/darius_whatsapp.py).

  darius.whatsapp.submit  retry of the (idempotent) task creation after a transient DARIUS failure
  darius.whatsapp.poll    self-rescheduling poll of a SUBMITTED link until a terminal state

Both are no-ops for a link that is already terminal, so a duplicated job can never act twice.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from jobs.registry import job_handler
from models.darius_whatsapp_task import SUBMITTED, SUBMITTING
from repositories.darius_whatsapp_task import DariusWhatsAppTaskRepository
from services import darius_whatsapp
from utils.config import get_settings


@job_handler(darius_whatsapp.SUBMIT_JOB)
async def submit_darius_task(db: AsyncSession, payload: dict) -> None:
    row = await DariusWhatsAppTaskRepository(db).get(int(payload["link_id"]))
    if row is None or row.status != SUBMITTING:
        return
    await darius_whatsapp.submit_link(db, get_settings(), row)


@job_handler(darius_whatsapp.POLL_JOB)
async def poll_darius_task(db: AsyncSession, payload: dict) -> None:
    row = await DariusWhatsAppTaskRepository(db).get(int(payload["link_id"]))
    if row is None or row.status != SUBMITTED:
        return
    await darius_whatsapp.poll_link(db, get_settings(), row)
