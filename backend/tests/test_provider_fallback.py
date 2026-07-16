"""Automatic provider switch: AgentExecutor retries once against
LLM_FALLBACK_PROVIDER when the primary provider raises mid-run."""

import pytest

from agents.executor import AgentExecutor
from agents.tools.base import ToolContext
from providers.llm.base import ChatMessage, LLMProvider, LLMResult
from providers.llm.factory import get_fallback_llm_provider


class FailingLLM(LLMProvider):
    name = "failing"

    @property
    def enabled(self) -> bool:
        return True

    async def chat(self, messages, tools=None) -> LLMResult:
        raise RuntimeError("provider is down")

    async def embed(self, text: str) -> list[float]:
        return [0.0]


class WorkingLLM(LLMProvider):
    name = "working"

    def __init__(self) -> None:
        self.calls = 0

    @property
    def enabled(self) -> bool:
        return True

    async def chat(self, messages, tools=None) -> LLMResult:
        self.calls += 1
        return LLMResult(content="resposta do provider de reserva")

    async def embed(self, text: str) -> list[float]:
        return [0.0]


@pytest.fixture
async def db_session(db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def user(db_session):
    from models.user import User

    user = User(email="fallback@example.com", full_name="Fallback", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_switches_to_fallback_provider_when_primary_raises(
    db_session, user, monkeypatch
):
    from utils.config import get_settings

    working = WorkingLLM()
    monkeypatch.setattr(get_settings(), "llm_fallback_provider", "anthropic")
    monkeypatch.setattr("providers.llm.factory._build", lambda name: working)
    get_fallback_llm_provider.cache_clear()
    try:
        executor = AgentExecutor(FailingLLM(), [])
        result = await executor.run(
            [ChatMessage(role="user", content="oi")],
            ToolContext(db=db_session, user=user),
        )
    finally:
        get_fallback_llm_provider.cache_clear()

    assert result.reply == "resposta do provider de reserva"
    assert working.calls == 1


@pytest.mark.asyncio
async def test_propagates_the_original_error_without_a_fallback_configured(
    db_session, user, monkeypatch
):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_fallback_provider", "")
    get_fallback_llm_provider.cache_clear()
    try:
        executor = AgentExecutor(FailingLLM(), [])
        with pytest.raises(RuntimeError, match="provider is down"):
            await executor.run(
                [ChatMessage(role="user", content="oi")],
                ToolContext(db=db_session, user=user),
            )
    finally:
        get_fallback_llm_provider.cache_clear()


@pytest.mark.asyncio
async def test_fallback_identical_to_primary_does_not_retry(
    db_session, user, monkeypatch
):
    """Guard against an infinite-seeming retry loop: if the configured
    fallback resolves to the same provider name as the primary, don't retry
    — just propagate, since a second call would fail identically."""
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_fallback_provider", "failing-configured")
    monkeypatch.setattr("providers.llm.factory._build", lambda name: FailingLLM())
    get_fallback_llm_provider.cache_clear()
    try:
        executor = AgentExecutor(FailingLLM(), [])
        with pytest.raises(RuntimeError, match="provider is down"):
            await executor.run(
                [ChatMessage(role="user", content="oi")],
                ToolContext(db=db_session, user=user),
            )
    finally:
        get_fallback_llm_provider.cache_clear()
