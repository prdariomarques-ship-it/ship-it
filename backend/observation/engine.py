"""Context Observation Engine: keeps one `CurrentContext` snapshot per user
in memory, rebuilt by `ObservationContextBuilder` and refreshed by the
Observation Scheduler (`observation/scheduler.py`) and by Event Bus activity
(`observation/events.py`).

`current()` is a synchronous, in-memory dict lookup — no I/O, no query, so
any decision point (the Cognitive Pipeline, a future autonomous Goal
executor, an admin view) can cheaply ask "what do we currently know" instead
of re-running seven queries on every call. This is the mechanism behind the
Context Observation Engine's success criterion: the system always knows its
current state before making a decision.

The cache is deliberately in-process and disposable, not a new source of
truth (see "Por que não existe um StateManager central", docs/architecture.md):
everything in a `CurrentContext` is re-derivable from Postgres at any time,
so losing the cache (restart, redeploy) loses nothing durable — the next
tick or triggering event rebuilds it. Restart-safety lives in *how* the
rebuild resumes (the durable job queue, see `observation/scheduler.py`), not
in persisting the snapshot itself.
"""

import asyncio
import time

from sqlalchemy.ext.asyncio import AsyncSession

from events.bus import event_bus
from models.user import User
from observability.metrics import record_observation_run
from observation.builder import ObservationContextBuilder
from observation.models import CurrentContext
from utils.logging import get_logger

logger = get_logger(__name__)


class ContextObservationEngine:
    def __init__(self, builder: ObservationContextBuilder | None = None) -> None:
        self._builder = builder or ObservationContextBuilder()
        self._snapshots: dict[int, CurrentContext] = {}
        # One lock per user avoids two concurrent observe() calls (a
        # scheduler tick and an event-triggered refresh landing at the same
        # time) racing to rebuild and publish out of order.
        self._locks: dict[int, asyncio.Lock] = {}

    def current(self, user_id: int) -> CurrentContext | None:
        """The last snapshot observed for this user, or None if none has
        been built yet (fresh process, before the first tick/seed)."""
        return self._snapshots.get(user_id)

    def is_stale(self, user_id: int, *, max_age_seconds: float) -> bool:
        """True if there is no snapshot yet, or the last one is older than
        `max_age_seconds` — a caller-defined freshness bar, since "stale"
        means different things to a dashboard vs. a decision about to act."""
        snapshot = self.current(user_id)
        return snapshot is None or snapshot.age_seconds() > max_age_seconds

    async def observe(
        self, db: AsyncSession, user: User, *, trigger: str = "scheduler"
    ) -> CurrentContext:
        """Rebuild the snapshot for `user`, cache it, and publish
        `observation.context_updated` so other components can react without
        polling `current()`."""
        lock = self._locks.setdefault(user.id, asyncio.Lock())
        async with lock:
            started = time.perf_counter()
            context = await self._builder.build(db, user, trigger=trigger)
            record_observation_run(trigger, time.perf_counter() - started)

            self._snapshots[user.id] = context
            await event_bus.publish(
                "observation.context_updated",
                {
                    "user_id": user.id,
                    "trigger": trigger,
                    "generated_at": context.generated_at.isoformat(),
                    "item_count": context.item_count,
                    "degraded_sources": context.degraded_sources,
                },
            )
            if context.degraded_sources:
                logger.warning(
                    "Observation snapshot for user %s degraded: %s",
                    user.id,
                    context.degraded_sources,
                )
            return context

    def reset(self) -> None:
        """Test-only: drop every cached snapshot and lock."""
        self._snapshots.clear()
        self._locks.clear()


context_observation_engine = ContextObservationEngine()
