"""Cognitive Pipeline: the Fase 4.2 entry point for "a message arrived, think
before acting."

Every stage from the brief is here, each one a small, independently testable
step — but none of them is a new architectural layer. They compose
components that already existed before this phase (Agent Registry, Tool
Registry, Event Bus, AI Orchestrator, Memory Manager) plus four new,
narrowly-scoped ones introduced alongside this file (`IntentEngine`,
`PriorityEngine`, `CognitivePlanner`, `ResponseValidator`, `LearningEngine`).
Execution itself is never reimplemented here — every plan step runs through
`orchestrator.service.ai_orchestrator.run`, the same single execution path
every other caller (chat, `/api/agents/{name}/run`) already uses.

    receive -> normalize -> intent -> priority -> load context (short-term +
    preferences + summary) -> memory (long-term) -> knowledge -> plan ->
    [per step: choose agent (Agent Registry) -> choose+execute tools (Tool
    Registry, inside AgentExecutor) -> validate -> retry once if needed] ->
    compose reply -> update memory (learning) -> record metrics -> return

Only the WhatsApp auto-reply job (`jobs.handlers.process_inbound_whatsapp_message`)
calls this today — callers that already choose an explicit agent (the chat
dashboard, `/api/agents/{name}/run`) keep calling `ai_orchestrator.run`
directly, unchanged, exactly as before this phase.
"""
import time

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agents.executor import ExecutedStep
from agents.registry import UnknownAgentError
from memory.manager import memory_manager
from models.message import MessageDirection
from models.user import User
from observability.metrics import (
    record_intent_classification,
    record_memory_lookup,
    record_pipeline_run,
    record_pipeline_stage,
    record_priority_classification,
    record_validation_retry,
)
from orchestrator.intent import Intent, IntentEngine, IntentResult
from orchestrator.learning import LearningEngine
from orchestrator.planning import CognitivePlanner, Plan, PlanStep, PlanStepStatus
from orchestrator.priority import Priority, PriorityEngine, PriorityResult
from orchestrator.service import ai_orchestrator
from orchestrator.validation import ResponseValidator
from providers.llm.base import ChatMessage, TokenUsage
from services.audit import record_log
from utils.logging import get_logger

logger = get_logger(__name__)

_MAX_VALIDATION_ATTEMPTS = 2  # first try + one bounded retry, never unbounded
_SHORT_TERM_LIMIT = 10
_LIGHT_INTENTS = (Intent.GREETING, Intent.SMALL_TALK)
_KNOWLEDGE_INTENTS = (Intent.RESEARCH, Intent.WEB_SEARCH, Intent.DOCUMENT, Intent.QUESTION)


def normalize_message(text: str) -> str:
    """Trim + collapse whitespace. Deliberately small: the LLM handles real
    language understanding: this stage only guards against noisy input
    (leading/trailing/duplicated whitespace) skewing intent detection."""
    return " ".join((text or "").split())


def _needs_deep_context(intent: IntentResult, priority: PriorityResult) -> bool:
    """Skip long-term/knowledge lookups for cheap, low-stakes messages —
    'avoid loading unnecessary context' from the brief, made concrete."""
    if priority.level in (Priority.HIGH, Priority.URGENT):
        return True
    return intent.top not in _LIGHT_INTENTS


class CognitiveResult(BaseModel):
    reply: str
    intent: IntentResult
    priority: PriorityResult
    plan: Plan
    steps: list[ExecutedStep] = []
    memories_used: int = 0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    duration_ms: float = 0.0
    validation_attempts: int = 0
    awaiting_confirmation: bool = False
    stage_durations_ms: dict[str, float] = {}


class CognitivePipeline:
    def __init__(
        self,
        intent_engine: IntentEngine | None = None,
        priority_engine: PriorityEngine | None = None,
        planner: CognitivePlanner | None = None,
        validator: ResponseValidator | None = None,
        learning: LearningEngine | None = None,
    ) -> None:
        self._intent_engine = intent_engine or IntentEngine()
        self._priority_engine = priority_engine or PriorityEngine()
        self._planner = planner or CognitivePlanner()
        self._validator = validator or ResponseValidator()
        self._learning = learning or LearningEngine()

    async def process(
        self, db: AsyncSession, user: User, message: str, contact_id: int | None = None
    ) -> CognitiveResult:
        started = time.perf_counter()
        stage_durations: dict[str, float] = {}

        async def timed(stage: str, awaitable):
            stage_started = time.perf_counter()
            result = await awaitable
            elapsed = time.perf_counter() - stage_started
            stage_durations[stage] = elapsed * 1000
            record_pipeline_stage(stage, elapsed)
            return result

        normalized = normalize_message(message)

        intent = await timed("intent", self._intent_engine.classify(normalized))
        record_intent_classification(intent.top.value)

        priority = await timed("priority", self._priority_engine.classify(normalized, intent))
        record_priority_classification(priority.level.value)

        history, extra_memories, memories_used = await timed(
            "load_context", self._load_context(db, contact_id, normalized, intent, priority)
        )

        plan = await timed("planning", self._planner.create_plan(normalized, intent, priority))

        if plan.needs_confirmation:
            reply = self._confirmation_reply(plan)
            await self._log_run(db, contact_id, intent, priority, plan, started, stage_durations)
            return CognitiveResult(
                reply=reply,
                intent=intent,
                priority=priority,
                plan=plan,
                memories_used=memories_used,
                duration_ms=(time.perf_counter() - started) * 1000,
                awaiting_confirmation=True,
                stage_durations_ms=stage_durations,
            )

        steps, usage, reply_parts, validation_attempts = await timed(
            "execution",
            self._execute_plan(db, user, contact_id, plan, extra_memories, history),
        )

        reply = self._compose_reply(reply_parts)

        await timed(
            "learning", self._learning.apply(db, contact_id, intent, priority, plan)
        )

        total_elapsed = time.perf_counter() - started
        record_pipeline_run(total_elapsed)
        await self._log_run(db, contact_id, intent, priority, plan, started, stage_durations, usage)

        return CognitiveResult(
            reply=reply,
            intent=intent,
            priority=priority,
            plan=plan,
            steps=steps,
            memories_used=memories_used,
            usage=usage,
            duration_ms=total_elapsed * 1000,
            validation_attempts=validation_attempts,
            stage_durations_ms=stage_durations,
        )

    async def _load_context(
        self,
        db: AsyncSession,
        contact_id: int | None,
        message: str,
        intent: IntentResult,
        priority: PriorityResult,
    ) -> tuple[list[ChatMessage], list[dict], int]:
        """Short-term history + preferences + summary always (cheap, local
        Postgres reads); long-term/knowledge semantic search only when the
        message actually warrants it."""
        history: list[ChatMessage] = []
        extra_memories: list[dict] = []

        if contact_id is not None:
            recent = await memory_manager.short_term(db, contact_id, limit=_SHORT_TERM_LIMIT)
            record_memory_lookup("short_term")
            history = [
                ChatMessage(
                    role="user" if entry.direction == MessageDirection.INBOUND else "assistant",
                    content=entry.content,
                )
                for entry in recent
                if entry.content
            ]

            preferences = await memory_manager.get_preferences(db, contact_id)
            record_memory_lookup("preferences")
            if preferences:
                extra_memories.append({"source": "preferences", "content": str(preferences)})

            summary = await memory_manager.get_summary(db, contact_id)
            record_memory_lookup("summary")
            if summary:
                extra_memories.append({"source": "summary", "content": summary})

        if _needs_deep_context(intent, priority):
            try:
                long_term = await memory_manager.long_term_search(message, contact_id)
                record_memory_lookup("long_term")
                extra_memories.extend(long_term)

                if intent.top in _KNOWLEDGE_INTENTS:
                    knowledge = await memory_manager.knowledge_search(message)
                    record_memory_lookup("knowledge")
                    extra_memories.extend(knowledge)
            except Exception as exc:  # noqa: BLE001 - memory is an enhancement, not a requirement
                logger.warning("Semantic memory lookup skipped (vector store unavailable): %s", exc)

        return history, extra_memories, len(extra_memories)

    async def _execute_plan(
        self,
        db: AsyncSession,
        user: User,
        contact_id: int | None,
        plan: Plan,
        memories: list[dict],
        history: list[ChatMessage],
    ) -> tuple[list[ExecutedStep], TokenUsage, list[str], int]:
        steps: list[ExecutedStep] = []
        usage = TokenUsage()
        reply_parts: list[str] = []
        total_attempts = 0

        for index, step in enumerate(plan.steps):
            blocked = any(
                dep < index and plan.steps[dep].status != PlanStepStatus.DONE for dep in step.depends_on
            )
            if blocked:
                step.status = PlanStepStatus.SKIPPED
                continue

            step.status = PlanStepStatus.RUNNING
            agent_result = None
            validation_ok = False
            attempt = 0
            while attempt < _MAX_VALIDATION_ATTEMPTS and not validation_ok:
                attempt += 1
                total_attempts += 1
                agent_result = await self._run_step(db, user, contact_id, step, memories, history)
                validation = self._validator.validate(reply=agent_result.reply, steps=agent_result.steps)
                validation_ok = validation.ok
                if not validation_ok and attempt < _MAX_VALIDATION_ATTEMPTS:
                    record_validation_retry()
                    logger.info("Retrying plan step (%s): %s", step.agent, validation.issues)

            step.status = PlanStepStatus.DONE if validation_ok else PlanStepStatus.FAILED
            step.result = agent_result.reply
            steps.extend(agent_result.steps)
            usage = usage + agent_result.usage
            if agent_result.reply.strip():
                reply_parts.append(agent_result.reply.strip())

        return steps, usage, reply_parts, total_attempts

    async def _run_step(self, db, user, contact_id, step: PlanStep, memories, history):
        try:
            return await ai_orchestrator.run(
                db=db,
                user=user,
                message=step.objective,
                agent_name=step.agent,
                contact_id=contact_id,
                memories=memories,
                history=history,
            )
        except UnknownAgentError:
            # The planner named an agent that no longer exists (hot-reload
            # race, hallucinated name) — fall back to the always-registered
            # generalist rather than dropping the step entirely.
            return await ai_orchestrator.run(
                db=db,
                user=user,
                message=step.objective,
                agent_name="assistant",
                contact_id=contact_id,
                memories=memories,
                history=history,
            )

    def _compose_reply(self, parts: list[str]) -> str:
        cleaned = [part for part in parts if part]
        if len(cleaned) <= 1:
            return cleaned[0] if cleaned else ""
        return "\n\n".join(cleaned)

    def _confirmation_reply(self, plan: Plan) -> str:
        lines = [f"{i + 1}. {step.objective} ({step.agent})" for i, step in enumerate(plan.steps)]
        return (
            "Antes de eu seguir em frente, confirma se é isso mesmo que você quer que eu faça?\n"
            + "\n".join(lines)
        )

    async def _log_run(self, db, contact_id, intent, priority, plan, started, stage_durations, usage=None):
        await record_log(
            db,
            source="cognitive_pipeline",
            message="Pipeline cognitivo concluído",
            payload={
                "contact_id": contact_id,
                "intent": intent.top.value,
                "intent_hypotheses": [h.model_dump() for h in intent.hypotheses],
                "priority": priority.level.value,
                "agents": [s.agent for s in plan.steps],
                "steps": len(plan.steps),
                "needs_confirmation": plan.needs_confirmation,
                "duration_ms": (time.perf_counter() - started) * 1000,
                "stage_durations_ms": stage_durations,
                "tokens": usage.total_tokens if usage else 0,
            },
        )


cognitive_pipeline = CognitivePipeline()
