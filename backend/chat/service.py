"""Chat orchestration: pick the agent, enrich with memory, run plan/execute."""
from sqlalchemy.ext.asyncio import AsyncSession

from agents.registry import get_agent
from chat.schemas import ChatRequest, ChatResponse
from memory.contact_memory import contact_memory_service
from models.user import User
from utils.logging import get_logger

logger = get_logger(__name__)


class ChatService:
    async def respond(self, db: AsyncSession, user: User, request: ChatRequest) -> ChatResponse:
        agent = get_agent(request.agent)

        memories: list[dict] = []
        try:
            context = await contact_memory_service.build_context(request.message, request.contact_id)
            memories = context["memories"]
        except Exception as exc:  # noqa: BLE001 - memory is an enhancement, not a requirement
            logger.warning("Memory lookup skipped (vector store unavailable): %s", exc)

        result = await agent.run(
            db=db,
            user=user,
            message=request.message,
            contact_id=request.contact_id,
            memories=memories,
        )
        return ChatResponse(
            agent=agent.name, reply=result.reply, steps=result.steps, memories_used=len(memories)
        )


chat_service = ChatService()
