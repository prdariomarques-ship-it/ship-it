"""Read-only admin view of the audited Telegram bot inventory.

No write endpoint exists on purpose: Dario OS does not hold Telegram credentials and must not start or
duplicate a bot (one `getUpdates` consumer per token). See `services/telegram_inventory.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from auth.permissions import require_admin
from services.telegram_inventory import TelegramInventory, build_inventory

router = APIRouter(prefix="/admin/telegram", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/bots", response_model=TelegramInventory)
async def telegram_bots() -> TelegramInventory:
    return build_inventory()
