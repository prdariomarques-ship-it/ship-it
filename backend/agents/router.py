from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agents.executor import ExecutedStep
from agents.registry import UnknownAgentError, get_agent, list_agents
from auth.dependencies import CurrentUser
from database.session import get_db

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentInfo(BaseModel):
    name: str
    description: str
    tools: list[str]


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=1)
    contact_id: int | None = None


class AgentRunResponse(BaseModel):
    agent: str
    reply: str
    steps: list[ExecutedStep] = []


@router.get("", response_model=list[AgentInfo])
async def get_agents(_: CurrentUser) -> list[AgentInfo]:
    return [
        AgentInfo(
            name=agent.name,
            description=agent.description,
            tools=[tool.name for tool in agent.tools],
        )
        for agent in list_agents()
    ]


@router.post("/{agent_name}/run", response_model=AgentRunResponse)
async def run_agent(
    agent_name: str,
    payload: AgentRunRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> AgentRunResponse:
    try:
        agent = get_agent(agent_name)
    except UnknownAgentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    result = await agent.run(
        db=db, user=current_user, message=payload.message, contact_id=payload.contact_id
    )
    return AgentRunResponse(agent=agent.name, reply=result.reply, steps=result.steps)
