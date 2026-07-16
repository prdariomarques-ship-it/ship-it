"""Function-calling loop: a scripted fake LLM drives real tools against the DB."""

import json

import pytest
from sqlalchemy import select

from agents.executor import AgentExecutor
from agents.tools.base import ToolContext
from agents.tools.productivity import create_task_tool, list_tasks_tool
from models.task import Task
from models.user import User
from providers.llm.base import ChatMessage, LLMProvider, LLMResult, ToolCallRequest


class ScriptedLLM(LLMProvider):
    """Fake provider that replays a fixed sequence of results."""

    name = "scripted"

    def __init__(self, script: list[LLMResult]) -> None:
        self._script = list(script)
        self.received: list[list[ChatMessage]] = []

    @property
    def enabled(self) -> bool:
        return True

    async def chat(self, messages, tools=None) -> LLMResult:
        self.received.append(list(messages))
        return self._script.pop(0)

    async def embed(self, text: str) -> list[float]:
        return [0.0]


@pytest.fixture
async def db_session(db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def user(db_session) -> User:
    user = User(email="exec@example.com", full_name="Exec", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_executor_runs_tool_calls_and_returns_final_answer(db_session, user):
    llm = ScriptedLLM(
        [
            LLMResult(
                tool_calls=[
                    ToolCallRequest(
                        id="call_1",
                        name="create_task",
                        arguments={"title": "Comprar pão", "priority": "high"},
                    )
                ]
            ),
            LLMResult(content="Tarefa criada: Comprar pão."),
        ]
    )
    executor = AgentExecutor(llm, [create_task_tool, list_tasks_tool])
    result = await executor.run(
        [ChatMessage(role="user", content="crie uma tarefa para comprar pão")],
        ToolContext(db=db_session, user=user),
    )

    assert result.reply == "Tarefa criada: Comprar pão."
    assert len(result.steps) == 1
    assert result.steps[0].tool == "create_task"
    assert json.loads(result.steps[0].result)["ok"] is True

    # The tool actually persisted the task.
    tasks = (await db_session.execute(select(Task))).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].title == "Comprar pão"
    assert tasks[0].user_id == user.id

    # The tool result was fed back to the model on the second call.
    second_call_messages = llm.received[1]
    assert any(
        m.role == "tool" and m.tool_call_id == "call_1" for m in second_call_messages
    )


@pytest.mark.asyncio
async def test_executor_reports_unknown_tool_to_model(db_session, user):
    llm = ScriptedLLM(
        [
            LLMResult(tool_calls=[ToolCallRequest(id="c1", name="nope", arguments={})]),
            LLMResult(content="ok"),
        ]
    )
    executor = AgentExecutor(llm, [create_task_tool])
    result = await executor.run(
        [ChatMessage(role="user", content="oi")], ToolContext(db=db_session, user=user)
    )
    assert result.steps[0].tool == "nope"
    assert "Unknown tool" in result.steps[0].result
    assert result.reply == "ok"


@pytest.mark.asyncio
async def test_executor_stops_at_iteration_budget(db_session, user):
    loop_result = LLMResult(
        tool_calls=[ToolCallRequest(id="c", name="list_tasks", arguments={})]
    )
    llm = ScriptedLLM([loop_result] * 6 + [LLMResult(content="resposta final")])
    executor = AgentExecutor(llm, [list_tasks_tool], max_iterations=6)
    result = await executor.run(
        [ChatMessage(role="user", content="oi")], ToolContext(db=db_session, user=user)
    )
    assert result.reply == "resposta final"
    assert len(result.steps) == 6
