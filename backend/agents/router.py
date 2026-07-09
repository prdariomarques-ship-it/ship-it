from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agents.registry import UnknownAgentError, get_agent, list_agents
from auth.dependencies import CurrentUser
from database.session import get_db

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentInfo(BaseModel):
    name: str
    description: str


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=1)


class AgentRunResponse(BaseModel):
    agent: str
    reply: str


@router.get("", response_model=list[AgentInfo])
async def get_agents(_: CurrentUser) -> list[AgentInfo]:
    return [AgentInfo(name=agent.name, description=agent.description) for agent in list_agents()]


@router.post("/{agent_name}/run", response_model=AgentRunResponse)
async def run_agent(
    agent_name: str,
    payload: AgentRunRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: CurrentUser,
) -> AgentRunResponse:
    try:
        agent = get_agent(agent_name)
    except UnknownAgentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    reply = await agent.run(db=db, message=payload.message)
    return AgentRunResponse(agent=agent.name, reply=reply)
