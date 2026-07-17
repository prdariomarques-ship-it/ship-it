"""CurrentContext: the system's own snapshot of "what's true right now" —
goals, tasks, calendar, recent events, conversations, pending work and
memory — built by `ObservationContextBuilder` and cached by
`ContextObservationEngine` (see `observation/builder.py`, `observation/engine.py`)
so any decision point can ask "what do we currently know" without
re-querying seven tables itself, satisfying the Context Observation Engine's
success criterion: the system always knows its current state before making
a decision.

Deliberately a plain, JSON-serializable snapshot, not a new source of truth
(see "Por que não existe um StateManager central", docs/architecture.md):
every field is derived from data that already lives in Postgres (goals,
tasks, calendar, logs, messages, jobs, embeddings). Losing it (process
restart, cache eviction) loses nothing durable — the next tick or triggering
event rebuilds it from the same tables. See docs/CURRENT_CONTEXT.md.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field

# Every dimension the Context Observation Engine aggregates, in the order
# CurrentContext exposes them. Kept as one tuple so builder/engine/tests
# iterate the same list instead of re-typing it.
DIMENSIONS: tuple[str, ...] = (
    "goals",
    "tasks",
    "calendar",
    "recent_events",
    "conversations",
    "pending_work",
    "memory",
)


class ContextItem(BaseModel):
    """One observed fact — same `{source, content}` shape
    `orchestrator.context.Context` already uses, so both context surfaces
    stay interchangeable wherever a caller just needs a flat list of facts."""

    source: str
    content: str


class CurrentContext(BaseModel):
    user_id: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # "scheduler" (periodic tick), "startup" (first seed) or "event:<name>"
    # (pulled forward by an EventBus trigger — see observation/events.py).
    trigger: str = "scheduler"

    goals: list[ContextItem] = Field(default_factory=list)
    tasks: list[ContextItem] = Field(default_factory=list)
    calendar: list[ContextItem] = Field(default_factory=list)
    recent_events: list[ContextItem] = Field(default_factory=list)
    conversations: list[ContextItem] = Field(default_factory=list)
    pending_work: list[ContextItem] = Field(default_factory=list)
    memory: list[ContextItem] = Field(default_factory=list)

    # Dimensions whose lookup failed and was skipped on this build — best
    # effort, same non-blocking philosophy as orchestrator.context.ContextBuilder:
    # a down dependency degrades one dimension, never the whole snapshot.
    degraded_sources: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any(getattr(self, dimension) for dimension in DIMENSIONS)

    @property
    def item_count(self) -> int:
        return sum(len(getattr(self, dimension)) for dimension in DIMENSIONS)

    def age_seconds(self, *, now: datetime | None = None) -> float:
        reference = now or datetime.now(timezone.utc)
        return (reference - self.generated_at).total_seconds()
