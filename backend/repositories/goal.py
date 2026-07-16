from datetime import datetime

from sqlalchemy import select

from models.goal import Goal, GoalDependency, GoalStatus
from repositories.base import SQLAlchemyRepository


class GoalRepository(SQLAlchemyRepository[Goal]):
    model = Goal

    async def dependency_ids(self, goal_id: int) -> list[int]:
        """Goals that `goal_id` itself depends on."""
        statement = select(GoalDependency.depends_on_id).where(GoalDependency.goal_id == goal_id)
        return list((await self.session.execute(statement)).scalars().all())

    async def is_blocked(self, goal_id: int) -> bool:
        """A goal is blocked while at least one of its dependencies isn't COMPLETED."""
        dep_ids = await self.dependency_ids(goal_id)
        if not dep_ids:
            return False
        statement = select(Goal.id).where(Goal.id.in_(dep_ids), Goal.status != GoalStatus.COMPLETED)
        incomplete = (await self.session.execute(statement)).scalars().all()
        return len(incomplete) > 0

    async def add_dependency(self, goal_id: int, depends_on_id: int) -> GoalDependency:
        dependency = GoalDependency(goal_id=goal_id, depends_on_id=depends_on_id)
        self.session.add(dependency)
        await self.session.commit()
        await self.session.refresh(dependency)
        return dependency

    async def remove_dependency(self, goal_id: int, depends_on_id: int) -> bool:
        statement = select(GoalDependency).where(
            GoalDependency.goal_id == goal_id, GoalDependency.depends_on_id == depends_on_id
        )
        dependency = (await self.session.execute(statement)).scalar_one_or_none()
        if dependency is None:
            return False
        await self.session.delete(dependency)
        await self.session.commit()
        return True

    async def recurrence_occurrences(self, recurrence_parent_id: int) -> list[Goal]:
        """Every spawned occurrence of a recurring goal, oldest first."""
        statement = (
            select(Goal)
            .where(Goal.recurrence_parent_id == recurrence_parent_id)
            .order_by(Goal.created_at.asc())
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def stuck_in_progress(self, updated_before: datetime, limit: int = 50) -> list[Goal]:
        """IN_PROGRESS goals that haven't had a progress update recently --
        the equivalent of JobRepository.stale_running_jobs for goals. Nothing
        yet consumes this automatically (goal execution isn't wired to an
        autonomous engine in this milestone — see docs/GOALS.md), but the
        query itself is what a future recovery routine would poll, and it's
        what proves goal state actually survives a restart: nothing but this
        row's own `updated_at` needs to be trusted to find work that stalled."""
        statement = (
            select(Goal)
            .where(Goal.status == GoalStatus.IN_PROGRESS, Goal.updated_at < updated_before)
            .order_by(Goal.updated_at.asc())
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())
