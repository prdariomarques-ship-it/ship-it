"""Chat orchestration: pick the agent, enrich with memory, call the LLM."""
from sqlalchemy.ext.asyncio import AsyncSession

from agents.registry import get_agent
from chat.schemas import ChatRequest, ChatResponse
from memory.service import memory_service
from utils.logging import get_logger

logger = get_logger(__name__)


class ChatService:
    async def respond(self, db: AsyncSession, request: ChatRequest) -> ChatResponse:
        agent = get_agent(request.agent)

        memories: list[dict] = []
        try:
            memories = await memory_service.search(
                query=request.message, limit=5, contact_id=request.contact_id
            )
        except Exception as exc:  # noqa: BLE001 - memory is an enhancement, not a requirement
            logger.warning("Memory lookup skipped (vector store unavailable): %s", exc)

        reply = await agent.run(db=db, message=request.message, memories=memories)
        return ChatResponse(agent=agent.name, reply=reply, memories_used=len(memories))


chat_service = ChatService()
