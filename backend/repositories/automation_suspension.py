from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from database.base import utcnow
from models.automation_suspension import AutomationSuspension
from repositories.base import SQLAlchemyRepository


class AutomationSuspensionRepository(SQLAlchemyRepository[AutomationSuspension]):
    model = AutomationSuspension

    async def get_by_scope(self, scope: str) -> AutomationSuspension | None:
        return await self.session.get(AutomationSuspension, scope)

    async def list_all(self) -> list[AutomationSuspension]:
        result = await self.session.execute(
            select(AutomationSuspension).order_by(AutomationSuspension.scope)
        )
        return list(result.scalars().all())

    async def scopes_in(self, scopes: list[str]) -> list[str]:
        """Which of `scopes` are currently suspended (one cheap indexed query)."""
        if not scopes:
            return []
        result = await self.session.execute(
            select(AutomationSuspension.scope).where(AutomationSuspension.scope.in_(scopes))
        )
        return list(result.scalars().all())

    async def suspend(self, scope: str, reason: str, actor_id: int | None) -> bool:
        """Create or refresh the suspension of `scope`. True when it was newly created.

        Atomic per scope: the INSERT is the arbiter. Losing the race to a
        concurrent identical request degrades to an UPDATE of reason/actor
        (last writer wins on the free-text reason only; the suspended state
        itself is already set either way).
        """
        self.session.add(AutomationSuspension(scope=scope, reason=reason, actor_id=actor_id))
        try:
            await self.session.commit()
            return True
        except IntegrityError:
            await self.session.rollback()
        existing = await self.get_by_scope(scope)
        if existing is None:  # deleted between the failed INSERT and the lookup: retry once
            self.session.add(AutomationSuspension(scope=scope, reason=reason, actor_id=actor_id))
            await self.session.commit()
            return True
        existing.reason = reason
        existing.actor_id = actor_id
        existing.updated_at = utcnow()
        await self.session.commit()
        return False

    async def resume(self, scope: str) -> bool:
        """Remove the suspension of `scope`. True when a row was actually removed."""
        result = cast(
            "CursorResult[Any]",
            await self.session.execute(
                delete(AutomationSuspension).where(AutomationSuspension.scope == scope)
            ),
        )
        await self.session.commit()
        return bool(result.rowcount)
