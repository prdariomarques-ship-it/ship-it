"""Context Builder: gathers everything the Cognitive Pipeline should know
before planning a reply.

Extracted from `CognitivePipeline._load_context` (Fase 4.2) into its own,
independently testable component -- same logic, not a rewrite, plus the
three owner-scoped sources (goals/calendar/tasks) that had never been wired
into the pipeline before. All three are cheap local Postgres reads (same
class as preferences/summary below), so they're gathered unconditionally --
no need for the semantic-search gate (`_needs_deep_context`) that exists
specifically to skip *expensive* long-term/knowledge lookups on cheap,
low-stakes messages.

Conversation history and preferences/summary stay scoped to `contact_id`
(the WhatsApp conversation); goals/calendar/tasks are scoped to `user.id`
(the instance owner) instead -- Dario OS is single-owner, and these three
domains were never contact-scoped to begin with (`Goal.user_id`,
`CalendarEvent.user_id`, `Task.user_id`).
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goals.service import GoalService
from memory.manager import memory_manager
from models.calendar import CalendarEvent
from models.goal import Goal
from models.message import MessageDirection
from models.task import Task, TaskStatus
from models.user import User
from observability.metrics import record_memory_lookup
from orchestrator.intent import Intent, IntentResult
from orchestrator.priority import Priority, PriorityResult
from providers.llm.base import ChatMessage
from repositories.base import SQLAlchemyRepository
from utils.logging import get_logger

logger = get_logger(__name__)

_SHORT_TERM_LIMIT = 10
_OWNER_CONTEXT_LIMIT = 5
_LIGHT_INTENTS = (Intent.GREETING, Intent.SMALL_TALK)
_KNOWLEDGE_INTENTS = (
    Intent.RESEARCH,
    Intent.WEB_SEARCH,
    Intent.DOCUMENT,
    Intent.QUESTION,
)


class _TaskRepo(SQLAlchemyRepository[Task]):
    model = Task


def needs_deep_context(intent: IntentResult, priority: PriorityResult) -> bool:
    """Skip long-term/knowledge lookups for cheap, low-stakes messages —
    'avoid loading unnecessary context' from the brief, made concrete."""
    if priority.level in (Priority.HIGH, Priority.URGENT):
        return True
    return intent.top not in _LIGHT_INTENTS


def _describe_goal(goal: Goal) -> str:
    parts = [goal.title, f"prioridade {goal.priority.value}"]
    if goal.deadline:
        parts.append(f"prazo {goal.deadline.date().isoformat()}")
    if goal.progress_percent:
        parts.append(f"{goal.progress_percent}% concluída")
    return "; ".join(parts)


def _describe_task(task: Task) -> str:
    parts = [task.title]
    if task.due_date:
        parts.append(f"prazo {task.due_date.date().isoformat()}")
    return "; ".join(parts)


def _describe_event(event: CalendarEvent) -> str:
    when = event.starts_at.isoformat()
    return f"{event.title} em {when}" + (
        f" ({event.location})" if event.location else ""
    )


class Context:
    def __init__(self, history: list[ChatMessage], memories: list[dict]) -> None:
        self.history = history
        self.memories = memories

    @property
    def memories_used(self) -> int:
        return len(self.memories)


class ContextBuilder:
    async def build(
        self,
        db: AsyncSession,
        user: User,
        contact_id: int | None,
        message: str,
        intent: IntentResult,
        priority: PriorityResult,
    ) -> Context:
        history: list[ChatMessage] = []
        memories: list[dict] = []

        if contact_id is not None:
            history, contact_memories = await self._gather_contact_context(
                db, contact_id
            )
            memories.extend(contact_memories)

        memories.extend(await self._gather_goals(db, user))
        memories.extend(await self._gather_tasks(db, user))
        memories.extend(await self._gather_calendar(db, user))

        if needs_deep_context(intent, priority):
            memories.extend(
                await self._gather_semantic_context(db, contact_id, message, intent)
            )

        return Context(history=history, memories=memories)

    async def _gather_contact_context(
        self, db: AsyncSession, contact_id: int
    ) -> tuple[list[ChatMessage], list[dict]]:
        recent = await memory_manager.short_term(
            db, contact_id, limit=_SHORT_TERM_LIMIT
        )
        record_memory_lookup("short_term")
        history = [
            ChatMessage(
                role="user"
                if entry.direction == MessageDirection.INBOUND
                else "assistant",
                content=entry.content,
            )
            for entry in recent
            if entry.content
        ]

        memories: list[dict] = []
        preferences = await memory_manager.get_preferences(db, contact_id)
        record_memory_lookup("preferences")
        if preferences:
            memories.append({"source": "preferences", "content": str(preferences)})

        summary = await memory_manager.get_summary(db, contact_id)
        record_memory_lookup("summary")
        if summary:
            memories.append({"source": "summary", "content": summary})

        return history, memories

    async def _gather_goals(self, db: AsyncSession, user: User) -> list[dict]:
        try:
            ready = await GoalService(db).ready_goals(
                user.id, limit=_OWNER_CONTEXT_LIMIT
            )
        except Exception as exc:  # noqa: BLE001 - context is an enhancement, never a requirement
            logger.warning("Goal context lookup skipped: %s", exc)
            return []
        record_memory_lookup("goal")
        return [{"source": "goal", "content": _describe_goal(goal)} for goal in ready]

    async def _gather_tasks(self, db: AsyncSession, user: User) -> list[dict]:
        try:
            tasks = await _TaskRepo(db).list(
                user_id=user.id, status=TaskStatus.PENDING, limit=_OWNER_CONTEXT_LIMIT
            )
        except Exception as exc:  # noqa: BLE001 - context is an enhancement, never a requirement
            logger.warning("Task context lookup skipped: %s", exc)
            return []
        record_memory_lookup("task")
        return [{"source": "task", "content": _describe_task(task)} for task in tasks]

    async def _gather_calendar(self, db: AsyncSession, user: User) -> list[dict]:
        try:
            statement = (
                select(CalendarEvent)
                .where(
                    CalendarEvent.user_id == user.id,
                    CalendarEvent.starts_at >= datetime.now(timezone.utc),
                )
                .order_by(CalendarEvent.starts_at.asc())
                .limit(_OWNER_CONTEXT_LIMIT)
            )
            events = list((await db.execute(statement)).scalars().all())
        except Exception as exc:  # noqa: BLE001 - context is an enhancement, never a requirement
            logger.warning("Calendar context lookup skipped: %s", exc)
            return []
        record_memory_lookup("calendar")
        return [
            {"source": "calendar", "content": _describe_event(event)}
            for event in events
        ]

    async def _gather_semantic_context(
        self,
        db: AsyncSession,
        contact_id: int | None,
        message: str,
        intent: IntentResult,
    ) -> list[dict]:
        try:
            long_term = await memory_manager.long_term_search(message, contact_id)
            record_memory_lookup("long_term")
            memories = list(long_term)

            if intent.top in _KNOWLEDGE_INTENTS:
                knowledge = await memory_manager.knowledge_search(message)
                record_memory_lookup("knowledge")
                memories.extend(knowledge)
            return memories
        except Exception as exc:  # noqa: BLE001 - memory is an enhancement, not a requirement
            logger.warning(
                "Semantic memory lookup skipped (vector store unavailable): %s", exc
            )
            return []
