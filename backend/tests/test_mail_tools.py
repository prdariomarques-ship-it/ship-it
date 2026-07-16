"""Gmail agent tools (Sprint 1) — unit, authorization and cross-user
isolation tests.

The isolation guarantee mirrors PROD-005: `_get_access_token` resolves a
mailbox strictly from `context.user.id` (set by the application, never by
the model). None of the four tool schemas even accept a user/mailbox
argument, so there is no parameter a manipulated LLM could supply to reach
someone else's inbox — these tests prove that in practice, not just by
reading the code.
"""

import json
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from agents.tools.base import ToolContext
from agents.tools.mail import (
    MailNotConnectedError,
    _get_access_token,
    _parse_date,
    detect_pending_email_actions_tool,
    read_email_thread_tool,
    search_emails_tool,
    summarize_email_thread_tool,
)
from models.email_account import EmailAccount
from models.user import User
from providers.llm.base import LLMResult, ToolCallRequest
from providers.mail.base import (
    EmailMessage,
    EmailSearchQuery,
    EmailThread,
    MailProvider,
    MailProviderError,
)
from repositories.email_account import EmailAccountRepository
from services.token_crypto import encrypt_token
from utils.config import get_settings


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "email_token_encryption_key", Fernet.generate_key().decode()
    )


@pytest.fixture
async def session_factory(db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def user_a(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="mail-a@example.com", full_name="A", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def user_b(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="mail-b@example.com", full_name="B", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _connect(
    session_factory, user: User, refresh_token: str, email_address: str
) -> EmailAccount:
    async with session_factory() as session:
        account = await EmailAccountRepository(session).create(
            user_id=user.id,
            provider="gmail",
            email_address=email_address,
            encrypted_refresh_token=encrypt_token(refresh_token),
            scopes=["gmail.readonly"],
            connected_at=datetime.now(timezone.utc),
        )
        return account


class FakeMailProvider(MailProvider):
    """Mailbox contents keyed by access token — access tokens are in turn
    keyed by refresh token (`"access-for-<refresh_token>"`), so a test can
    prove which mailbox a tool call actually reached without touching
    Google at all."""

    name = "gmail"

    def __init__(self, mailboxes: dict[str, list[EmailMessage]] | None = None) -> None:
        self.mailboxes = mailboxes or {}
        self.search_calls: list[str] = []
        self.thread_calls: list[str] = []

    def authorization_url(self, state: str) -> str:
        raise NotImplementedError

    async def exchange_code(self, code: str):
        raise NotImplementedError

    async def refresh_access_token(self, refresh_token: str):
        from providers.mail.base import OAuthTokens

        return OAuthTokens(access_token=f"access-for-{refresh_token}")

    async def search(
        self, access_token: str, query: EmailSearchQuery
    ) -> list[EmailMessage]:
        self.search_calls.append(access_token)
        return self.mailboxes.get(access_token, [])

    async def get_thread(self, access_token: str, thread_id: str) -> EmailThread:
        self.thread_calls.append(access_token)
        for message in self.mailboxes.get(access_token, []):
            if message.thread_id == thread_id:
                return EmailThread(
                    id=thread_id, subject=message.subject, messages=[message]
                )
        # Gmail itself scopes threads by the authorized mailbox — a thread_id
        # belonging to a *different* mailbox simply doesn't exist for this
        # access_token, exactly like a real 404 from the Gmail API.
        raise MailProviderError(f"thread {thread_id} not found")


def _message(mailbox_tag: str) -> EmailMessage:
    return EmailMessage(
        id=f"m-{mailbox_tag}",
        thread_id=f"t-{mailbox_tag}",
        sender=f"someone@{mailbox_tag}.example.com",
        subject=f"Assunto {mailbox_tag}",
        snippet=f"conteúdo confidencial de {mailbox_tag}",
        body=f"corpo confidencial de {mailbox_tag}",
    )


# --- _get_access_token: the sole authorization chokepoint ----------------------
@pytest.mark.asyncio
async def test_get_access_token_resolves_strictly_from_context_user_id(
    session_factory, user_a, user_b, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")
    await _connect(session_factory, user_b, "rt-b", "b@gmail.com")
    monkeypatch.setattr(
        "agents.tools.mail.get_mail_provider", lambda: FakeMailProvider()
    )

    async with session_factory() as session:
        token_a = await _get_access_token(ToolContext(db=session, user=user_a))
    async with session_factory() as session:
        token_b = await _get_access_token(ToolContext(db=session, user=user_b))

    assert token_a == "access-for-rt-a"
    assert token_b == "access-for-rt-b"


# --- _parse_date -----------------------------------------------------------------
def test_parse_date_attaches_utc_to_a_naive_date():
    assert _parse_date("2026-01-15") == datetime(2026, 1, 15, tzinfo=timezone.utc)


def test_parse_date_converts_an_offset_aware_datetime_to_utc_instead_of_discarding_it():
    assert _parse_date("2026-01-15T10:00:00-03:00") == datetime(
        2026, 1, 15, 13, 0, tzinfo=timezone.utc
    )


def test_parse_date_returns_none_for_garbage():
    assert _parse_date("not-a-date") is None
    assert _parse_date(None) is None


@pytest.mark.asyncio
async def test_get_access_token_raises_when_user_has_no_connected_account(
    session_factory, user_a
):
    async with session_factory() as session:
        with pytest.raises(MailNotConnectedError):
            await _get_access_token(ToolContext(db=session, user=user_a))


@pytest.mark.asyncio
async def test_get_access_token_treats_a_revoked_refresh_token_as_not_connected(
    session_factory, user_a, monkeypatch
):
    """A refresh token the user revoked in their Google account (or that
    simply expired) must surface the same actionable "reconnect" message as
    never having connected — not a raw provider error the model can't act
    on."""
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")

    class _RevokedProvider(FakeMailProvider):
        async def refresh_access_token(self, refresh_token):
            raise MailProviderError("invalid_grant: token has been revoked")

    monkeypatch.setattr(
        "agents.tools.mail.get_mail_provider", lambda: _RevokedProvider()
    )

    async with session_factory() as session:
        with pytest.raises(MailNotConnectedError, match="reconectar"):
            await _get_access_token(ToolContext(db=session, user=user_a))


@pytest.mark.asyncio
async def test_search_emails_tool_surfaces_a_revoked_token_as_a_clean_tool_error(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")

    class _RevokedProvider(FakeMailProvider):
        async def refresh_access_token(self, refresh_token):
            raise MailProviderError("invalid_grant")

    monkeypatch.setattr(
        "agents.tools.mail.get_mail_provider", lambda: _RevokedProvider()
    )

    async with session_factory() as session:
        result = await search_emails_tool.run(ToolContext(db=session, user=user_a), {})

    payload = json.loads(result)
    assert "error" in payload
    assert "reconectar" in payload["error"]


# --- authorization: tools reject cleanly when nothing is connected -------------
@pytest.mark.asyncio
async def test_search_emails_tool_rejects_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        result = await search_emails_tool.run(ToolContext(db=session, user=user_a), {})
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_read_email_thread_tool_rejects_when_not_connected(
    session_factory, user_a
):
    async with session_factory() as session:
        result = await read_email_thread_tool.run(
            ToolContext(db=session, user=user_a), {"thread_id": "t-1"}
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_summarize_email_thread_tool_rejects_when_not_connected(
    session_factory, user_a
):
    async with session_factory() as session:
        result = await summarize_email_thread_tool.run(
            ToolContext(db=session, user=user_a), {"thread_id": "t-1"}
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_detect_pending_email_actions_tool_rejects_when_not_connected(
    session_factory, user_a
):
    async with session_factory() as session:
        result = await detect_pending_email_actions_tool.run(
            ToolContext(db=session, user=user_a), {}
        )
    assert "error" in json.loads(result)


# --- isolation: two connected users, zero cross-user leakage -------------------
@pytest.mark.asyncio
async def test_search_emails_tool_never_returns_another_users_mailbox(
    session_factory, user_a, user_b, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")
    await _connect(session_factory, user_b, "rt-b", "b@gmail.com")
    provider = FakeMailProvider(
        {"access-for-rt-a": [_message("a")], "access-for-rt-b": [_message("b")]}
    )
    monkeypatch.setattr("agents.tools.mail.get_mail_provider", lambda: provider)

    async with session_factory() as session:
        result_a = await search_emails_tool.run(
            ToolContext(db=session, user=user_a), {}
        )
    async with session_factory() as session:
        result_b = await search_emails_tool.run(
            ToolContext(db=session, user=user_b), {}
        )

    payload_a = json.loads(result_a)
    payload_b = json.loads(result_b)
    assert [m["id"] for m in payload_a["messages"]] == ["m-a"]
    assert [m["id"] for m in payload_b["messages"]] == ["m-b"]
    # Every request actually reached the mailbox derived from its own user.
    assert provider.search_calls == ["access-for-rt-a", "access-for-rt-b"]


@pytest.mark.asyncio
async def test_read_email_thread_tool_cannot_be_pointed_at_another_users_thread(
    session_factory, user_a, user_b, monkeypatch
):
    """Even if the model supplies a thread_id that belongs to user A's
    mailbox, user B's tool call must not return it — the access token used
    is derived only from user B's own connected account."""
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")
    await _connect(session_factory, user_b, "rt-b", "b@gmail.com")
    provider = FakeMailProvider(
        {"access-for-rt-a": [_message("a")], "access-for-rt-b": [_message("b")]}
    )
    monkeypatch.setattr("agents.tools.mail.get_mail_provider", lambda: provider)

    async with session_factory() as session:
        result = await read_email_thread_tool.run(
            ToolContext(db=session, user=user_b), {"thread_id": "t-a"}
        )

    payload = json.loads(result)
    assert "error" in payload  # not found under B's mailbox — no leak, no crash
    assert "confidencial de a" not in result


@pytest.mark.asyncio
async def test_read_email_thread_tool_returns_the_requesting_users_own_thread(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")
    provider = FakeMailProvider({"access-for-rt-a": [_message("a")]})
    monkeypatch.setattr("agents.tools.mail.get_mail_provider", lambda: provider)

    async with session_factory() as session:
        result = await read_email_thread_tool.run(
            ToolContext(db=session, user=user_a), {"thread_id": "t-a"}
        )

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["messages"][0]["body"] == "corpo confidencial de a"


@pytest.mark.asyncio
async def test_search_emails_tool_maps_provider_error_to_a_tool_error(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")

    class _FailingProvider(FakeMailProvider):
        async def search(self, access_token, query):
            raise MailProviderError("gmail is down")

    monkeypatch.setattr(
        "agents.tools.mail.get_mail_provider", lambda: _FailingProvider()
    )

    async with session_factory() as session:
        result = await search_emails_tool.run(ToolContext(db=session, user=user_a), {})
    assert "error" in json.loads(result)


# --- summarize_email_thread: LLM-backed ------------------------------------------
@pytest.mark.asyncio
async def test_summarize_email_thread_tool_calls_the_llm_and_returns_its_summary(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")
    provider = FakeMailProvider({"access-for-rt-a": [_message("a")]})
    monkeypatch.setattr("agents.tools.mail.get_mail_provider", lambda: provider)

    class _FakeLLM:
        async def chat(self, messages, tools=None):
            return LLMResult(content="Resumo: pendência de resposta.")

    monkeypatch.setattr("agents.tools.mail.get_llm_provider", lambda: _FakeLLM())

    async with session_factory() as session:
        result = await summarize_email_thread_tool.run(
            ToolContext(db=session, user=user_a), {"thread_id": "t-a"}
        )

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["summary"] == "Resumo: pendência de resposta."


@pytest.mark.asyncio
async def test_summarize_email_thread_tool_empty_thread_skips_the_llm_call(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")
    provider = FakeMailProvider({"access-for-rt-a": []})

    async def _empty_get_thread(access_token, thread_id):
        return EmailThread(id=thread_id, subject="", messages=[])

    provider.get_thread = _empty_get_thread
    monkeypatch.setattr("agents.tools.mail.get_mail_provider", lambda: provider)

    calls = {"n": 0}

    class _CountingLLM:
        async def chat(self, messages, tools=None):
            calls["n"] += 1
            return LLMResult(content="should not be called")

    monkeypatch.setattr("agents.tools.mail.get_llm_provider", lambda: _CountingLLM())

    async with session_factory() as session:
        result = await summarize_email_thread_tool.run(
            ToolContext(db=session, user=user_a), {"thread_id": "t-a"}
        )

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["summary"] == ""
    assert calls["n"] == 0


# --- detect_pending_email_actions: function-calling extraction -----------------
@pytest.mark.asyncio
async def test_detect_pending_actions_tool_reports_actions_from_the_llm_tool_call(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")
    provider = FakeMailProvider({"access-for-rt-a": [_message("a")]})
    monkeypatch.setattr("agents.tools.mail.get_mail_provider", lambda: provider)

    class _FakeLLM:
        async def chat(self, messages, tools=None):
            return LLMResult(
                tool_calls=[
                    ToolCallRequest(
                        id="call_1",
                        name="report_pending_actions",
                        arguments={
                            "actions": [
                                {
                                    "type": "respond",
                                    "description": "Responder sobre a proposta",
                                    "thread_id": "t-a",
                                    "subject": "Assunto a",
                                }
                            ]
                        },
                    )
                ]
            )

    monkeypatch.setattr("agents.tools.mail.get_llm_provider", lambda: _FakeLLM())

    async with session_factory() as session:
        result = await detect_pending_email_actions_tool.run(
            ToolContext(db=session, user=user_a), {}
        )

    payload = json.loads(result)
    assert payload["ok"] is True
    assert len(payload["actions"]) == 1
    assert payload["actions"][0]["type"] == "respond"


@pytest.mark.asyncio
async def test_detect_pending_actions_tool_no_tool_call_returns_empty_list(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")
    provider = FakeMailProvider({"access-for-rt-a": [_message("a")]})
    monkeypatch.setattr("agents.tools.mail.get_mail_provider", lambda: provider)

    class _SilentLLM:
        async def chat(self, messages, tools=None):
            return LLMResult(content="nada pendente")

    monkeypatch.setattr("agents.tools.mail.get_llm_provider", lambda: _SilentLLM())

    async with session_factory() as session:
        result = await detect_pending_email_actions_tool.run(
            ToolContext(db=session, user=user_a), {}
        )

    assert json.loads(result) == {"ok": True, "actions": []}


@pytest.mark.asyncio
async def test_detect_pending_actions_tool_no_messages_skips_the_llm_call(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a@gmail.com")
    provider = FakeMailProvider({"access-for-rt-a": []})
    monkeypatch.setattr("agents.tools.mail.get_mail_provider", lambda: provider)

    calls = {"n": 0}

    class _CountingLLM:
        async def chat(self, messages, tools=None):
            calls["n"] += 1
            return LLMResult(content="unused")

    monkeypatch.setattr("agents.tools.mail.get_llm_provider", lambda: _CountingLLM())

    async with session_factory() as session:
        result = await detect_pending_email_actions_tool.run(
            ToolContext(db=session, user=user_a), {}
        )

    assert json.loads(result) == {"ok": True, "actions": []}
    assert calls["n"] == 0
