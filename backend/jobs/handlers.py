"""Built-in job handlers."""
from sqlalchemy.ext.asyncio import AsyncSession

from jobs.registry import job_handler
from memory.contact_memory import contact_memory_service
from providers.whatsapp.factory import get_whatsapp_provider
from utils.logging import get_logger
from workflows.service import workflow_service

logger = get_logger(__name__)


@job_handler("contact.summarize")
async def summarize_contact(db: AsyncSession, payload: dict) -> None:
    """Refresh a contact's automatic profile summary."""
    await contact_memory_service.summarize_contact(db, int(payload["contact_id"]))


@job_handler("whatsapp.send_text")
async def send_whatsapp_text(db: AsyncSession, payload: dict) -> None:
    """Send a WhatsApp text through the configured provider (with queue retry)."""
    await get_whatsapp_provider().send_text(str(payload["to"]), str(payload["content"]))


@job_handler("workflow.trigger")
async def trigger_workflow(db: AsyncSession, payload: dict) -> None:
    """Fire an n8n workflow; queue retries cover transient n8n outages."""
    await workflow_service.trigger(str(payload["workflow"]), dict(payload.get("data", {})))
