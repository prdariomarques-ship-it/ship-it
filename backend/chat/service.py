"""Chat orchestration: translate a ChatRequest into an agent run.

Agent selection, memory and tool execution all live in the AI Orchestrator;
this service only adapts between the chat wire format and that call.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from chat.schemas import ChatRequest, ChatResponse
from models.user import User
from orchestrator.service import ai_orchestrator


class ChatService:
    async def respond(
        self, db: AsyncSession, user: User, request: ChatRequest
    ) -> ChatResponse:
        result = await ai_orchestrator.run(
            db=db,
            user=user,
            message=request.message,
            agent_name=request.agent,
            contact_id=request.contact_id,
        )
        return ChatResponse(
            agent=request.agent,
            reply=result.reply,
            steps=result.steps,
            memories_used=result.memories_used,
        )


chat_service = ChatService()
