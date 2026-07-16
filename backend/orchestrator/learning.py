"""Learning: what the Cognitive Pipeline keeps after a conversation ends.

Message embedding and periodic profile summarization are NOT duplicated
here — they already happen on every inbound/outbound message via
`ContactMemoryService.record_interaction` (called from the webhook and from
`services/messaging.py::persist_outbound_message`). This module adds the one
thing that infrastructure doesn't cover: noticing which *domains* a contact
tends to need (a lightweight, structural pattern — not free-form fact
extraction) and tagging the contact with them, via the existing
`Contact.categories` field. Every write is deduplicated by
`MemoryManager.add_categories` itself, so a repeat conversation about the
same domain never grows the list — "avoid redundant storage" is enforced at
the storage boundary, not by the caller remembering to check.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from memory.manager import memory_manager
from orchestrator.intent import IntentResult
from orchestrator.planning import Plan
from orchestrator.priority import PriorityResult
from services.audit import record_log

_AGENT_CATEGORY: dict[str, str] = {
    "store": "loja",
    "church": "igreja",
    "personal": "pessoal",
    "content": "conteudo",
}


class LearningEngine:
    async def apply(
        self,
        db: AsyncSession,
        contact_id: int | None,
        intent: IntentResult,
        priority: PriorityResult,
        plan: Plan,
    ) -> list[str]:
        if contact_id is None:
            return []

        candidates = {
            _AGENT_CATEGORY[step.agent]
            for step in plan.steps
            if step.agent in _AGENT_CATEGORY
        }
        added = (
            await memory_manager.add_categories(db, contact_id, sorted(candidates))
            if candidates
            else []
        )

        await record_log(
            db,
            source="cognitive_pipeline.learning",
            message="Aprendizado da conversa registrado",
            payload={
                "contact_id": contact_id,
                "intent": intent.top.value,
                "priority": priority.level.value,
                "categories_added": added,
            },
        )
        return added
