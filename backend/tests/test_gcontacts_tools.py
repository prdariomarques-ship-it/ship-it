"""Google Contacts agent tools (Sprint 2) — unit, authorization and
cross-user isolation tests. Mirrors `tests/test_gcalendar_tools.py`.
"""

import json
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from agents.tools.base import ToolContext
from agents.tools.gcontacts import (
    ContactsNotConnectedError,
    _get_access_token,
    create_google_contact_tool,
    delete_google_contact_tool,
    search_google_contacts_tool,
    update_google_contact_tool,
)
from models.gcontacts_account import GoogleContactsAccount
from models.user import User
from providers.contacts.base import Contact, ContactsProvider, ContactsProviderError
from repositories.gcontacts_account import GoogleContactsAccountRepository
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
        user = User(email="con-a@example.com", full_name="A", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def user_b(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="con-b@example.com", full_name="B", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _connect(
    session_factory, user: User, refresh_token: str, label: str
) -> GoogleContactsAccount:
    async with session_factory() as session:
        return await GoogleContactsAccountRepository(session).create(
            user_id=user.id,
            provider="google",
            account_label=label,
            encrypted_refresh_token=encrypt_token(refresh_token),
            scopes=["contacts"],
            connected_at=datetime.now(timezone.utc),
        )


def _contact(tag: str, resource_name: str = "people/c1") -> Contact:
    return Contact(
        resource_name=resource_name,
        display_name=f"Contato confidencial de {tag}",
        given_name=tag,
        emails=[f"{tag}@example.com"],
        phones=[f"+55{tag}"],
    )


class FakeContactsProvider(ContactsProvider):
    name = "google"

    def __init__(
        self, contacts_by_token: dict[str, list[Contact]] | None = None
    ) -> None:
        self.contacts_by_token = contacts_by_token or {}
        self.calls: list[str] = []

    def authorization_url(self, state: str) -> str:
        raise NotImplementedError

    async def exchange_code(self, code: str):
        raise NotImplementedError

    async def refresh_access_token(self, refresh_token: str):
        from providers.contacts.base import OAuthTokens

        return OAuthTokens(access_token=f"access-for-{refresh_token}")

    async def search_contacts(self, access_token: str, query) -> list[Contact]:
        self.calls.append(access_token)
        return self.contacts_by_token.get(access_token, [])

    async def get_contact(self, access_token: str, resource_name: str) -> Contact:
        self.calls.append(access_token)
        for contact in self.contacts_by_token.get(access_token, []):
            if contact.resource_name == resource_name:
                return contact
        raise ContactsProviderError("not found")

    async def create_contact(self, access_token: str, contact) -> Contact:
        self.calls.append(access_token)
        return _contact("new", "people/new")

    async def update_contact(
        self, access_token: str, resource_name: str, update
    ) -> Contact:
        self.calls.append(access_token)
        # Mirrors the real GoogleContactsProvider: fetch first (for the
        # etag) — this is what actually enforces the isolation boundary,
        # since Google's People API scopes resourceNames by access_token.
        await self.get_contact(access_token, resource_name)
        return _contact("updated", resource_name)

    async def delete_contact(self, access_token: str, resource_name: str) -> None:
        self.calls.append(access_token)


# --- _get_access_token -----------------------------------------------------------
@pytest.mark.asyncio
async def test_get_access_token_resolves_strictly_from_context_user_id(
    session_factory, user_a, user_b, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    await _connect(session_factory, user_b, "rt-b", "b")
    monkeypatch.setattr(
        "agents.tools.gcontacts.get_contacts_provider", lambda: FakeContactsProvider()
    )

    async with session_factory() as session:
        token_a = await _get_access_token(ToolContext(db=session, user=user_a))
    async with session_factory() as session:
        token_b = await _get_access_token(ToolContext(db=session, user=user_b))

    assert token_a == "access-for-rt-a"
    assert token_b == "access-for-rt-b"


@pytest.mark.asyncio
async def test_get_access_token_raises_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        with pytest.raises(ContactsNotConnectedError):
            await _get_access_token(ToolContext(db=session, user=user_a))


@pytest.mark.asyncio
async def test_get_access_token_treats_a_revoked_refresh_token_as_not_connected(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")

    class _RevokedProvider(FakeContactsProvider):
        async def refresh_access_token(self, refresh_token):
            raise ContactsProviderError("invalid_grant")

    monkeypatch.setattr(
        "agents.tools.gcontacts.get_contacts_provider", lambda: _RevokedProvider()
    )
    async with session_factory() as session:
        with pytest.raises(ContactsNotConnectedError, match="reconectar"):
            await _get_access_token(ToolContext(db=session, user=user_a))


# --- authorization -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_contacts_tool_rejects_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        result = await search_google_contacts_tool.run(
            ToolContext(db=session, user=user_a), {}
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_create_contact_tool_rejects_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        result = await create_google_contact_tool.run(
            ToolContext(db=session, user=user_a), {"given_name": "X"}
        )
    assert "error" in json.loads(result)


# --- isolation: two connected users, zero cross-user leakage -----------------------
@pytest.mark.asyncio
async def test_search_contacts_tool_never_returns_another_users_address_book(
    session_factory, user_a, user_b, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    await _connect(session_factory, user_b, "rt-b", "b")
    provider = FakeContactsProvider(
        {"access-for-rt-a": [_contact("a")], "access-for-rt-b": [_contact("b")]}
    )
    monkeypatch.setattr(
        "agents.tools.gcontacts.get_contacts_provider", lambda: provider
    )

    async with session_factory() as session:
        result_a = await search_google_contacts_tool.run(
            ToolContext(db=session, user=user_a), {}
        )
    async with session_factory() as session:
        result_b = await search_google_contacts_tool.run(
            ToolContext(db=session, user=user_b), {}
        )

    contacts_a = json.loads(result_a)["contacts"]
    contacts_b = json.loads(result_b)["contacts"]
    assert contacts_a[0]["display_name"] == "Contato confidencial de a"
    assert contacts_b[0]["display_name"] == "Contato confidencial de b"
    assert provider.calls == ["access-for-rt-a", "access-for-rt-b"]


@pytest.mark.asyncio
async def test_update_contact_tool_cannot_be_pointed_at_another_users_contact(
    session_factory, user_a, user_b, monkeypatch
):
    """Even if the model supplies a resource_name that belongs to user A's
    address book, user B's tool call must not update it — the access token
    used is derived only from user B's own connected account, and Google's
    People API itself scopes resourceNames by access_token (identical to
    the thread_id isolation already proven for Gmail)."""
    await _connect(session_factory, user_a, "rt-a", "a")
    await _connect(session_factory, user_b, "rt-b", "b")
    provider = FakeContactsProvider(
        {
            "access-for-rt-a": [_contact("a", "people/c-a")],
            "access-for-rt-b": [_contact("b", "people/c-b")],
        }
    )
    monkeypatch.setattr(
        "agents.tools.gcontacts.get_contacts_provider", lambda: provider
    )

    async with session_factory() as session:
        result = await update_google_contact_tool.run(
            ToolContext(db=session, user=user_b),
            {"resource_name": "people/c-a", "given_name": "Hacked"},
        )
    payload = json.loads(result)
    assert "error" in payload  # not found under B's address book — no leak, no crash


@pytest.mark.asyncio
async def test_create_contact_tool_uses_the_requesting_users_own_address_book(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeContactsProvider()
    monkeypatch.setattr(
        "agents.tools.gcontacts.get_contacts_provider", lambda: provider
    )

    async with session_factory() as session:
        result = await create_google_contact_tool.run(
            ToolContext(db=session, user=user_a), {"given_name": "Novo Contato"}
        )
    payload = json.loads(result)
    assert payload["ok"] is True
    assert provider.calls == ["access-for-rt-a"]


@pytest.mark.asyncio
async def test_search_contacts_tool_maps_provider_error_to_a_tool_error(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")

    class _FailingProvider(FakeContactsProvider):
        async def search_contacts(self, access_token, query):
            raise ContactsProviderError("google is down")

    monkeypatch.setattr(
        "agents.tools.gcontacts.get_contacts_provider", lambda: _FailingProvider()
    )
    async with session_factory() as session:
        result = await search_google_contacts_tool.run(
            ToolContext(db=session, user=user_a), {}
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_delete_contact_tool_success(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeContactsProvider()
    monkeypatch.setattr(
        "agents.tools.gcontacts.get_contacts_provider", lambda: provider
    )
    async with session_factory() as session:
        result = await delete_google_contact_tool.run(
            ToolContext(db=session, user=user_a), {"resource_name": "people/c1"}
        )
    assert json.loads(result)["deleted"] is True
