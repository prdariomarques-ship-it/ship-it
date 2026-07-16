"""GoalManager: create, prioritize, transition status, manage dependencies,
approval and recurrence for persistent goals.

Deliberately does not decide *how* a goal gets worked on (that would be the
Orchestrator/Planner deciding which agent runs which step) -- this is the
persistence, lifecycle and coordination-surface layer. Every meaningful
transition publishes to the shared EventBus and is recorded as an audit
entry (`GET /api/goals/{id}/history`), so other components (or a future
autonomous execution engine) can react without polling. See docs/GOALS.md
for the full scope boundary.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from goals.events import goal_event_publisher
from goals.scoring import priority_score
from models.goal import Goal, GoalPriority, GoalStatus
from repositories.goal import GoalRepository
from utils.logging import get_logger

logger = get_logger(__name__)


class CyclicDependencyError(ValueError):
    """Adding this dependency would make two (or more) goals depend on each other."""


class ApprovalRequiredError(ValueError):
    """The goal is still AWAITING_APPROVAL; only GoalService.approve_goal can move it on."""


class GoalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.goals = GoalRepository(session)

    async def create_goal(
        self,
        user_id: int,
        title: str,
        description: str | None = None,
        priority: GoalPriority = GoalPriority.MEDIUM,
        deadline: datetime | None = None,
        recurrence_interval_days: int | None = None,
        requires_approval: bool = False,
    ) -> Goal:
        initial_status = GoalStatus.AWAITING_APPROVAL if requires_approval else GoalStatus.PENDING
        goal = await self.goals.create(
            user_id=user_id,
            title=title,
            description=description,
            priority=priority,
            deadline=deadline,
            recurrence_interval_days=recurrence_interval_days,
            requires_approval=requires_approval,
            status=initial_status,
        )
        await goal_event_publisher.publish(self.session, goal, "created")
        return goal

    async def approve_goal(self, goal: Goal, approved_by_id: int) -> Goal:
        """The human-approval gate: only a goal AWAITING_APPROVAL can be approved,
        and only this method (never the generic status-update path) can move
        it out of that status."""
        if goal.status != GoalStatus.AWAITING_APPROVAL:
            raise ApprovalRequiredError(f"Goal {goal.id} is not awaiting approval (status={goal.status.value})")
        updated = await self.goals.update(
            goal,
            status=GoalStatus.PENDING,
            approved_at=datetime.now(timezone.utc),
            approved_by_id=approved_by_id,
        )
        await goal_event_publisher.publish(self.session, updated, "approved")
        return updated

    async def add_dependency(self, goal_id: int, depends_on_id: int) -> None:
        if goal_id == depends_on_id:
            raise CyclicDependencyError("A goal cannot depend on itself")
        if await self._creates_cycle(goal_id, depends_on_id):
            raise CyclicDependencyError(
                f"Goal {depends_on_id} already (directly or transitively) depends on goal {goal_id}"
            )
        await self.goals.add_dependency(goal_id, depends_on_id)

    async def _creates_cycle(self, goal_id: int, depends_on_id: int) -> bool:
        """True if `goal_id` is reachable by walking depends_on_id's own
        dependency chain -- i.e. depends_on_id already (transitively) depends
        on goal_id, so adding goal_id -> depends_on_id would close a loop."""
        visited: set[int] = set()
        queue = [depends_on_id]
        while queue:
            current = queue.pop()
            if current == goal_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            queue.extend(await self.goals.dependency_ids(current))
        return False

    async def is_ready(self, goal_id: int) -> bool:
        return not await self.goals.is_blocked(goal_id)

    async def ready_goals(self, user_id: int, limit: int = 50) -> list[Goal]:
        """PENDING goals (never AWAITING_APPROVAL) with every dependency
        already COMPLETED, ordered by priority_score (highest/most urgent
        first)."""
        pending = await self.goals.list(user_id=user_id, status=GoalStatus.PENDING, limit=200)
        ready = [goal for goal in pending if not await self.goals.is_blocked(goal.id)]
        ready.sort(key=priority_score, reverse=True)
        return ready[:limit]

    async def update_status(self, goal: Goal, status: GoalStatus) -> Goal:
        """Transition a goal's status. Completing a recurring goal spawns its
        next occurrence instead of resetting this row, so history is kept.

        A goal AWAITING_APPROVAL can only be CANCELLED (rejected) through this
        path -- moving it forward requires `approve_goal`, which is the whole
        point of the approval gate."""
        if goal.status == GoalStatus.AWAITING_APPROVAL and status != GoalStatus.CANCELLED:
            raise ApprovalRequiredError(
                f"Goal {goal.id} requires approval before its status can change to {status.value}"
            )
        updated = await self.goals.update(goal, status=status)
        await goal_event_publisher.publish(self.session, updated, "status_changed")

        if status == GoalStatus.COMPLETED:
            await self._remember_completion(updated)
            if updated.recurrence_interval_days:
                await self._spawn_next_occurrence(updated)
        return updated

    async def update_progress(self, goal: Goal, progress_percent: int) -> Goal:
        clamped = max(0, min(100, progress_percent))
        updated = await self.goals.update(goal, progress_percent=clamped)
        await goal_event_publisher.publish(self.session, updated, "progress_updated")
        return updated

    async def _remember_completion(self, goal: Goal) -> None:
        """Best-effort: record the completion as a memory so agents can recall
        past goals in conversation. Never blocks or fails goal completion --
        Qdrant being unavailable is a real, already-seen scenario elsewhere
        in the codebase, not hypothetical."""
        try:
            from memory.manager import memory_manager

            await memory_manager.remember(
                self.session,
                content=f"Meta concluída: {goal.title}",
                source="goal",
            )
        except Exception:  # noqa: BLE001 - memory write is best-effort, never blocks completion
            logger.warning("Failed to record memory for completed goal %s", goal.id, exc_info=True)

    async def _spawn_next_occurrence(self, goal: Goal) -> Goal:
        assert goal.recurrence_interval_days is not None, "caller must only invoke this for recurring goals"
        base = goal.deadline or datetime.now(timezone.utc)
        next_deadline = base + timedelta(days=goal.recurrence_interval_days)
        next_goal = await self.goals.create(
            user_id=goal.user_id,
            title=goal.title,
            description=goal.description,
            priority=goal.priority,
            deadline=next_deadline,
            recurrence_interval_days=goal.recurrence_interval_days,
            recurrence_parent_id=goal.recurrence_parent_id or goal.id,
        )
        await goal_event_publisher.publish(self.session, next_goal, "created", detail="recurrence")
        return next_goal
