from datetime import datetime

from sqlalchemy import func, select

from models.task import Task, TaskStatus
from repositories.base import SQLAlchemyRepository


class TaskRepository(SQLAlchemyRepository[Task]):
    model = Task

    async def overdue_counts_by_contact(
        self, user_id: int, contact_ids: list[int], *, now: datetime
    ) -> dict[int, int]:
        """One GROUP BY query for every contact in `contact_ids` -- never
        one COUNT per contact. Feeds the cross-contact priority ranking
        (see CONTACT_INTELLIGENCE_ARCHITECTURE.md #13); contacts with zero
        overdue tasks are simply absent from the returned dict."""
        if not contact_ids:
            return {}
        statement = (
            select(Task.contact_id, func.count())
            .where(
                Task.user_id == user_id,
                Task.contact_id.in_(contact_ids),
                Task.status == TaskStatus.PENDING,
                Task.due_date.is_not(None),
                Task.due_date < now,
            )
            .group_by(Task.contact_id)
        )
        rows = (await self.session.execute(statement)).all()
        return {contact_id: count for contact_id, count in rows}
