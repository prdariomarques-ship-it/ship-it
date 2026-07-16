"""Goal lifecycle events: published on the shared EventBus and persisted to
the logs table (audit trail / execution history survives even with nobody
subscribed) -- same idiom as `jobs/events.py::JobEventPublisher`.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from events.bus import event_bus
from models.goal import Goal
from services.audit import record_log


class GoalEventPublisher:
    async def publish(
        self, db: AsyncSession, goal: Goal, event: str, detail: str = ""
    ) -> None:
        payload = {
            "goal_id": goal.id,
            "user_id": goal.user_id,
            "title": goal.title,
            "status": goal.status.value,
            "priority": goal.priority.value,
            "progress_percent": goal.progress_percent,
            "detail": detail,
        }
        await record_log(
            db,
            source=f"goal:{goal.id}",
            message=f"Goal {goal.id} {event}",
            level="info",
            payload=payload,
        )
        await event_bus.publish(f"goal.{event}", payload)


goal_event_publisher = GoalEventPublisher()
