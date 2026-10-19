from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from models.darius_whatsapp_task import DariusWhatsAppTask
from repositories.base import SQLAlchemyRepository


class DariusWhatsAppTaskRepository(SQLAlchemyRepository[DariusWhatsAppTask]):
    model = DariusWhatsAppTask

    async def get_by_key(self, dedupe_key: str) -> DariusWhatsAppTask | None:
        return await self.find_one(dedupe_key=dedupe_key)

    async def claim(
        self, *, dedupe_key: str, message_id: int, contact_id: int, instance: str, control_revision: int | None
    ) -> tuple[DariusWhatsAppTask, bool]:
        """Insert the link, or return the existing one. The UNIQUE dedupe_key is the arbiter.

        Returns (row, created). Two concurrent callers for the same message get
        exactly one `created=True`.
        """
        row = DariusWhatsAppTask(
            dedupe_key=dedupe_key, message_id=message_id, contact_id=contact_id, instance=instance,
            control_revision=control_revision, history=[],
        )
        try:
            # SAVEPOINT: losing the UNIQUE race must not roll back (and thereby expire) the caller's
            # session -- the job handler still holds the contact and message it is working with.
            async with self.session.begin_nested():
                self.session.add(row)
        except IntegrityError:
            existing = await self.get_by_key(dedupe_key)
            if existing is None:  # pragma: no cover - UNIQUE violated by a row deleted meanwhile
                raise
            return existing, False
        await self.session.commit()
        await self.session.refresh(row)
        return row, True

    async def save(self, row: DariusWhatsAppTask) -> DariusWhatsAppTask:
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_recent(
        self, *, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[DariusWhatsAppTask]:
        statement = select(DariusWhatsAppTask)
        if status:
            statement = statement.where(DariusWhatsAppTask.status == status)
        result = await self.session.execute(
            statement.order_by(DariusWhatsAppTask.id.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def counts_by_status(self) -> dict[str, int]:
        result = await self.session.execute(
            select(DariusWhatsAppTask.status, func.count()).group_by(DariusWhatsAppTask.status)
        )
        return {status: count for status, count in result.all()}
