from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agents.registry import UnknownAgentError
from auth.dependencies import CurrentUser
from chat.schemas import ChatRequest, ChatResponse
from chat.service import chat_service
from database.session import get_db

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: CurrentUser,
) -> ChatResponse:
    try:
        return await chat_service.respond(db, payload)
    except UnknownAgentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
