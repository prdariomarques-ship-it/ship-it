"""Google Drive agent tools (Sprint 3) — unit, authorization, isolation,
indexing/RAG-integration and concurrency tests.

Qdrant isn't reachable in this suite (same as everywhere else memory is
touched), so `memory_manager.remember`/`forget` are mocked here — these
tests prove the *indexing* logic (chunking, staleness detection, stale-
chunk replacement, citation content) calls the existing Memory Manager
correctly, not that Qdrant itself works (already covered by
`tests/test_memory_service_delete.py` and the pre-existing memory suite).
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from agents.tools.base import ToolContext
from agents.tools.gdrive import (
    DriveNotConnectedError,
    _get_access_token,
    index_google_drive_file_tool,
    index_google_drive_folder_tool,
    list_google_drive_files_tool,
    read_google_drive_file_tool,
    search_google_drive_files_tool,
    summarize_google_drive_document_tool,
    update_google_drive_index_tool,
)
from models.gdrive_account import GoogleDriveAccount
from models.user import User
from providers.drive.base import DriveFile, DriveProvider, DriveProviderError, UnsupportedDriveFileTypeError
from repositories.gdrive_account import GoogleDriveAccountRepository
from repositories.gdrive_indexed_file import GoogleDriveIndexedFileRepository
from services.token_crypto import encrypt_token
from utils.config import get_settings


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "email_token_encryption_key", Fernet.generate_key().decode())


@pytest.fixture
async def session_factory(db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def user_a(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="drive-a@example.com", full_name="A", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def user_b(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="drive-b@example.com", full_name="B", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _connect(session_factory, user: User, refresh_token: str, label: str) -> GoogleDriveAccount:
    async with session_factory() as session:
        return await GoogleDriveAccountRepository(session).create(
            user_id=user.id,
            provider="google",
            account_label=label,
            encrypted_refresh_token=encrypt_token(refresh_token),
            scopes=["drive.readonly"],
            connected_at=datetime.now(timezone.utc),
        )


def _file(tag: str, file_id: str = "f1", modified: datetime | None = None) -> DriveFile:
    return DriveFile(
        id=file_id,
        name=f"Documento confidencial de {tag}.txt",
        mime_type="text/plain",
        size=100,
        modified_time=modified or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class FakeDriveProvider(DriveProvider):
    """Files keyed by access token, content keyed by file id — access
    tokens are `access-for-<refresh_token>`, so a test can prove which
    Drive a tool call actually reached without touching Google at all."""

    name = "google"

    def __init__(self, files_by_token: dict[str, list[DriveFile]] | None = None, text_by_file: dict[str, str] | None = None) -> None:
        self.files_by_token = files_by_token or {}
        self.text_by_file = text_by_file or {}
        self.calls: list[str] = []

    def authorization_url(self, state: str) -> str:
        raise NotImplementedError

    async def exchange_code(self, code: str):
        raise NotImplementedError

    async def refresh_access_token(self, refresh_token: str):
        from providers.drive.base import OAuthTokens

        return OAuthTokens(access_token=f"access-for-{refresh_token}")

    async def list_files(self, access_token: str, folder_id=None, limit: int = 20) -> list[DriveFile]:
        self.calls.append(access_token)
        return self.files_by_token.get(access_token, [])

    async def search_files(self, access_token: str, query) -> list[DriveFile]:
        self.calls.append(access_token)
        return self.files_by_token.get(access_token, [])

    async def get_metadata(self, access_token: str, file_id: str) -> DriveFile:
        self.calls.append(access_token)
        for file in self.files_by_token.get(access_token, []):
            if file.id == file_id:
                return file
        raise DriveProviderError("not found")

    async def read_file_text(self, access_token: str, file_id: str) -> str:
        self.calls.append(access_token)
        await self.get_metadata(access_token, file_id)  # enforces the same isolation boundary as the real provider
        return self.text_by_file.get(file_id, "")


# --- _get_access_token -----------------------------------------------------------
@pytest.mark.asyncio
async def test_get_access_token_resolves_strictly_from_context_user_id(session_factory, user_a, user_b, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    await _connect(session_factory, user_b, "rt-b", "b")
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: FakeDriveProvider())

    async with session_factory() as session:
        token_a = await _get_access_token(ToolContext(db=session, user=user_a))
    async with session_factory() as session:
        token_b = await _get_access_token(ToolContext(db=session, user=user_b))

    assert token_a == "access-for-rt-a"
    assert token_b == "access-for-rt-b"


@pytest.mark.asyncio
async def test_get_access_token_raises_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        with pytest.raises(DriveNotConnectedError):
            await _get_access_token(ToolContext(db=session, user=user_a))


@pytest.mark.asyncio
async def test_get_access_token_treats_a_revoked_refresh_token_as_not_connected(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")

    class _RevokedProvider(FakeDriveProvider):
        async def refresh_access_token(self, refresh_token):
            raise DriveProviderError("invalid_grant")

    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: _RevokedProvider())
    async with session_factory() as session:
        with pytest.raises(DriveNotConnectedError, match="reconectar"):
            await _get_access_token(ToolContext(db=session, user=user_a))


# --- authorization -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_files_tool_rejects_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        result = await list_google_drive_files_tool.run(ToolContext(db=session, user=user_a), {})
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_search_files_tool_rejects_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        result = await search_google_drive_files_tool.run(ToolContext(db=session, user=user_a), {})
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_read_file_tool_rejects_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        result = await read_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f1"})
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_index_file_tool_rejects_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        result = await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f1"})
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_update_index_tool_rejects_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        result = await update_google_drive_index_tool.run(ToolContext(db=session, user=user_a), {})
    assert "error" in json.loads(result)


# --- isolation: two connected users, zero cross-user leakage -------------------
@pytest.mark.asyncio
async def test_search_files_tool_never_returns_another_users_drive(session_factory, user_a, user_b, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    await _connect(session_factory, user_b, "rt-b", "b")
    provider = FakeDriveProvider({"access-for-rt-a": [_file("a")], "access-for-rt-b": [_file("b")]})
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)

    async with session_factory() as session:
        result_a = await search_google_drive_files_tool.run(ToolContext(db=session, user=user_a), {})
    async with session_factory() as session:
        result_b = await search_google_drive_files_tool.run(ToolContext(db=session, user=user_b), {})

    files_a = json.loads(result_a)["files"]
    files_b = json.loads(result_b)["files"]
    assert "confidencial de a" in files_a[0]["name"]
    assert "confidencial de b" in files_b[0]["name"]
    assert provider.calls == ["access-for-rt-a", "access-for-rt-b"]


@pytest.mark.asyncio
async def test_read_file_tool_cannot_be_pointed_at_another_users_file(session_factory, user_a, user_b, monkeypatch):
    """Even if the model supplies a file_id that belongs to user A's Drive,
    user B's tool call must not read it — the access token used is derived
    only from user B's own connected account, and Google's Drive API itself
    scopes file ids by access_token (identical to the thread_id/event_id/
    resource_name isolation already proven for the other three domains)."""
    await _connect(session_factory, user_a, "rt-a", "a")
    await _connect(session_factory, user_b, "rt-b", "b")
    provider = FakeDriveProvider(
        {"access-for-rt-a": [_file("a", "f-a")], "access-for-rt-b": [_file("b", "f-b")]},
        {"f-a": "conteúdo secreto de a"},
    )
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)

    async with session_factory() as session:
        result = await read_google_drive_file_tool.run(ToolContext(db=session, user=user_b), {"file_id": "f-a"})
    payload = json.loads(result)
    assert "error" in payload
    assert "secreto" not in result


@pytest.mark.asyncio
async def test_search_files_tool_maps_provider_error_to_a_tool_error(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")

    class _FailingProvider(FakeDriveProvider):
        async def search_files(self, access_token, query):
            raise DriveProviderError("google is down")

    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: _FailingProvider())
    async with session_factory() as session:
        result = await search_google_drive_files_tool.run(ToolContext(db=session, user=user_a), {})
    assert "error" in json.loads(result)


# --- indexing: writes into the existing Memory Manager / Knowledge Store -------
@pytest.mark.asyncio
async def test_index_file_tool_stores_content_via_the_existing_memory_manager(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeDriveProvider(
        {"access-for-rt-a": [_file("a", "f-a")]}, {"f-a": "Conteúdo do documento sobre investimentos."}
    )
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)

    remember = AsyncMock(return_value=1)
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.remember", remember)

    async with session_factory() as session:
        result = await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-a"})

    payload = json.loads(result)
    assert payload["indexed"] is True
    assert payload["chunks"] == 1
    remember.assert_awaited_once()
    call_kwargs = remember.call_args.kwargs
    assert call_kwargs["source"] == "knowledge"
    assert "Documento confidencial de a.txt" in call_kwargs["content"]
    assert "Conteúdo do documento sobre investimentos." in call_kwargs["content"]


@pytest.mark.asyncio
async def test_index_file_tool_records_bookkeeping_and_skips_unchanged_reindex(
    session_factory, user_a, db_engine, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeDriveProvider({"access-for-rt-a": [_file("a", "f-a")]}, {"f-a": "conteúdo"})
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.remember", AsyncMock(return_value=1))

    async with session_factory() as session:
        first = json.loads(await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-a"}))
    assert first["indexed"] is True

    async with session_factory() as session:
        second = json.loads(await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-a"}))
    assert second["indexed"] is False
    assert "sem alterações" in second["reason"]


@pytest.mark.asyncio
async def test_index_file_tool_replaces_stale_chunks_when_file_changed(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new_time = old_time + timedelta(days=1)
    provider = FakeDriveProvider({"access-for-rt-a": [_file("a", "f-a", modified=old_time)]}, {"f-a": "versão 1"})
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.remember", AsyncMock(return_value=1))
    forget = AsyncMock()
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.forget", forget)

    async with session_factory() as session:
        await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-a"})

    # File changed on Drive: newer modified_time, new content.
    provider.files_by_token["access-for-rt-a"] = [_file("a", "f-a", modified=new_time)]
    provider.text_by_file["f-a"] = "versão 2"

    async with session_factory() as session:
        result = json.loads(await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-a"}))

    assert result["indexed"] is True
    forget.assert_awaited_once()
    assert forget.call_args.args[1] == [1]


@pytest.mark.asyncio
async def test_index_file_tool_rejects_unsupported_file_types(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")

    class _UnsupportedProvider(FakeDriveProvider):
        async def read_file_text(self, access_token, file_id):
            await self.get_metadata(access_token, file_id)
            raise UnsupportedDriveFileTypeError("tipo não suportado")

    provider = _UnsupportedProvider({"access-for-rt-a": [_file("a", "f-a")]})
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)

    async with session_factory() as session:
        result = await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-a"})
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_index_file_tool_skips_empty_files_without_calling_memory_manager(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeDriveProvider({"access-for-rt-a": [_file("a", "f-empty")]}, {"f-empty": "   "})
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)
    remember = AsyncMock(return_value=1)
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.remember", remember)

    async with session_factory() as session:
        result = json.loads(
            await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-empty"})
        )
    assert result["indexed"] is False
    assert "vazio" in result["reason"]
    remember.assert_not_awaited()


@pytest.mark.asyncio
async def test_index_folder_tool_records_failed_files_without_stopping(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeDriveProvider(
        {"access-for-rt-a": [_file("a", "f-ok"), _file("a", "f-bad")]}, {"f-ok": "conteúdo bom"}
    )

    original_read = provider.read_file_text

    async def flaky_read(access_token, file_id):
        if file_id == "f-bad":
            raise DriveProviderError("corrupted")
        return await original_read(access_token, file_id)

    provider.read_file_text = flaky_read
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.remember", AsyncMock(return_value=1))

    async with session_factory() as session:
        result = json.loads(
            await index_google_drive_folder_tool.run(ToolContext(db=session, user=user_a), {"folder_id": "folder-1"})
        )
    assert [item["file_id"] for item in result["indexed"]] == ["f-ok"]
    assert [item["file_id"] for item in result["failed"]] == ["f-bad"]


@pytest.mark.asyncio
async def test_index_folder_tool_aggregates_indexed_and_skipped(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeDriveProvider(
        {"access-for-rt-a": [_file("a", "f-1"), _file("a", "f-2")]},
        {"f-1": "conteúdo 1", "f-2": "conteúdo 2"},
    )
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.remember", AsyncMock(return_value=1))

    async with session_factory() as session:
        result = json.loads(
            await index_google_drive_folder_tool.run(ToolContext(db=session, user=user_a), {"folder_id": "folder-1"})
        )
    assert len(result["indexed"]) == 2
    assert result["failed"] == []


@pytest.mark.asyncio
async def test_update_index_tool_reindexes_only_changed_files(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    provider = FakeDriveProvider(
        {"access-for-rt-a": [_file("a", "f-1", modified=old_time), _file("a", "f-2", modified=old_time)]},
        {"f-1": "v1", "f-2": "v1"},
    )
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.remember", AsyncMock(return_value=1))
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.forget", AsyncMock())

    async with session_factory() as session:
        await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-1"})
        await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-2"})

    # Only f-1 changes on Drive.
    new_time = old_time + timedelta(days=1)
    provider.files_by_token["access-for-rt-a"] = [
        _file("a", "f-1", modified=new_time),
        _file("a", "f-2", modified=old_time),
    ]
    provider.text_by_file["f-1"] = "v2"

    async with session_factory() as session:
        result = json.loads(await update_google_drive_index_tool.run(ToolContext(db=session, user=user_a), {}))

    assert [item["file_id"] for item in result["updated"]] == ["f-1"]
    assert [item["file_id"] for item in result["unchanged"]] == ["f-2"]
    assert result["checked"] == 2


@pytest.mark.asyncio
async def test_update_index_tool_records_failed_files_without_stopping(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    provider = FakeDriveProvider(
        {"access-for-rt-a": [_file("a", "f-1", modified=old_time), _file("a", "f-2", modified=old_time)]},
        {"f-1": "v1", "f-2": "v1"},
    )
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.remember", AsyncMock(return_value=1))
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.forget", AsyncMock())

    async with session_factory() as session:
        await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-1"})
        await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-2"})

    # f-2 was deleted from Drive since it was indexed.
    provider.files_by_token["access-for-rt-a"] = [_file("a", "f-1", modified=old_time)]

    async with session_factory() as session:
        result = json.loads(await update_google_drive_index_tool.run(ToolContext(db=session, user=user_a), {}))

    assert [item["file_id"] for item in result["failed"]] == ["f-2"]
    assert [item["file_id"] for item in result["unchanged"]] == ["f-1"]


@pytest.mark.asyncio
async def test_summarize_document_tool_empty_content_skips_the_llm_call(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeDriveProvider({"access-for-rt-a": [_file("a", "f-empty")]}, {"f-empty": "   "})
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)

    calls = {"n": 0}

    class _CountingLLM:
        async def chat(self, messages, tools=None):
            calls["n"] += 1
            from providers.llm.base import LLMResult

            return LLMResult(content="should not be called")

    monkeypatch.setattr("agents.tools.gdrive.get_llm_provider", lambda: _CountingLLM())

    async with session_factory() as session:
        result = json.loads(
            await summarize_google_drive_document_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-empty"})
        )
    assert result["summary"] == ""
    assert calls["n"] == 0


# --- concurrency: indexing bookkeeping race -------------------------------------
@pytest.mark.asyncio
async def test_indexed_file_upsert_recovers_from_concurrent_race(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    original_get = GoogleDriveIndexedFileRepository.get_by_user_and_file
    calls = {"count": 0}

    async def racy_get(self, uid, file_id):
        calls["count"] += 1
        if calls["count"] <= 2:
            return None
        return await original_get(self, uid, file_id)

    monkeypatch.setattr(GoogleDriveIndexedFileRepository, "get_by_user_and_file", racy_get)

    async with session_factory() as session:
        first = await GoogleDriveIndexedFileRepository(session).upsert_for_user_and_file(
            user_a.id, "f-race", file_name="x", mime_type="text/plain",
            modified_time=datetime.now(timezone.utc), embedding_ids=[1], indexed_at=datetime.now(timezone.utc),
        )
    async with session_factory() as session:
        second = await GoogleDriveIndexedFileRepository(session).upsert_for_user_and_file(
            user_a.id, "f-race", file_name="x", mime_type="text/plain",
            modified_time=datetime.now(timezone.utc), embedding_ids=[2], indexed_at=datetime.now(timezone.utc),
        )
    assert first.id == second.id
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_concurrent_reindexing_of_the_same_file_does_not_orphan_embeddings(
    session_factory, user_a, monkeypatch
):
    """Two overlapping reindex calls for the *same* file (e.g. `index_google_drive_folder`
    and `update_google_drive_index` racing, or the same request retried) must not leave
    one call's freshly-embedded chunks referenced by nothing — a permanent leak in the
    Knowledge Store that never gets cleaned up on a later reindex (which only forgets
    whatever the *current* bookkeeping row points to).

    Simulated deterministically: task A completes a full reindex first; task B's own
    staleness check is forced to see the *pre-A* snapshot (as it would if B started
    before A finished), while every other read sees real, current data — exactly what
    true concurrent execution would produce, without relying on asyncio scheduling
    order.
    """
    from types import SimpleNamespace

    await _connect(session_factory, user_a, "rt-a", "a")
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new_time = old_time + timedelta(days=1)

    async with session_factory() as session:
        await GoogleDriveIndexedFileRepository(session).create(
            user_id=user_a.id,
            file_id="f-a",
            file_name="doc.txt",
            mime_type="text/plain",
            modified_time=old_time,
            embedding_ids=[100, 101],
            indexed_at=old_time,
        )
    stale_snapshot = SimpleNamespace(modified_time=old_time, embedding_ids=[100, 101], indexed_at=old_time)

    provider = FakeDriveProvider({"access-for-rt-a": [_file("a", "f-a", modified=new_time)]}, {"f-a": "novo conteúdo"})
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)

    created_ids = {"n": 200}
    forgotten: list[list[int]] = []

    async def fake_remember(db, content, source):
        created_ids["n"] += 1
        return created_ids["n"]

    async def fake_forget(db, embedding_ids):
        forgotten.append(list(embedding_ids))

    monkeypatch.setattr("agents.tools.gdrive.memory_manager.remember", fake_remember)
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.forget", fake_forget)

    from agents.tools.gdrive import _index_one

    async with session_factory() as session:
        await _index_one(ToolContext(db=session, user=user_a), provider, "access-for-rt-a", "f-a")

    original_get = GoogleDriveIndexedFileRepository.get_by_user_and_file
    calls = {"n": 0}

    async def controlled_get(self, uid, fid):
        calls["n"] += 1
        # Task B's own staleness check (the first read _index_one performs) sees
        # the state from before task A ran — exactly what a true race produces.
        if calls["n"] == 1:
            return stale_snapshot
        return await original_get(self, uid, fid)

    monkeypatch.setattr(GoogleDriveIndexedFileRepository, "get_by_user_and_file", controlled_get)

    async with session_factory() as session:
        await _index_one(ToolContext(db=session, user=user_a), provider, "access-for-rt-a", "f-a")

    async with session_factory() as session:
        final = await GoogleDriveIndexedFileRepository(session).get_by_user_and_file(user_a.id, "f-a")

    all_forgotten = {embedding_id for batch in forgotten for embedding_id in batch}
    task_a_ids = {201}  # single chunk, task A's remember() call
    orphaned = task_a_ids - set(final.embedding_ids) - all_forgotten
    assert orphaned == set(), (
        f"task A's embeddings {task_a_ids} are neither referenced by the final row "
        f"({final.embedding_ids}) nor forgotten ({all_forgotten}) — permanently orphaned"
    )


# --- summarize ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_summarize_document_tool_calls_the_llm(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeDriveProvider({"access-for-rt-a": [_file("a", "f-a")]}, {"f-a": "conteúdo do documento"})
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)

    from providers.llm.base import LLMResult

    class _FakeLLM:
        async def chat(self, messages, tools=None):
            return LLMResult(content="Resumo do documento.")

    monkeypatch.setattr("agents.tools.gdrive.get_llm_provider", lambda: _FakeLLM())

    async with session_factory() as session:
        result = await summarize_google_drive_document_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-a"})
    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["summary"] == "Resumo do documento."


# --- multiusuário: each user's indexing reads only their own Drive -------------
@pytest.mark.asyncio
async def test_multiuser_indexing_each_reads_only_their_own_drive(session_factory, user_a, user_b, monkeypatch):
    """Dario OS's knowledge base is deliberately global (single-owner
    system, same as `knowledge_search` today) — what must stay isolated is
    *which Drive* gets read, never the resulting knowledge partition. This
    proves user B indexing never touches user A's Drive content, even
    though both entries land in the same Knowledge Store afterwards."""
    await _connect(session_factory, user_a, "rt-a", "a")
    await _connect(session_factory, user_b, "rt-b", "b")
    provider = FakeDriveProvider(
        {"access-for-rt-a": [_file("a", "f-a")], "access-for-rt-b": [_file("b", "f-b")]},
        {"f-a": "conteúdo de a", "f-b": "conteúdo de b"},
    )
    monkeypatch.setattr("agents.tools.gdrive.get_drive_provider", lambda: provider)
    remember = AsyncMock(return_value=1)
    monkeypatch.setattr("agents.tools.gdrive.memory_manager.remember", remember)

    async with session_factory() as session:
        await index_google_drive_file_tool.run(ToolContext(db=session, user=user_a), {"file_id": "f-a"})
    async with session_factory() as session:
        await index_google_drive_file_tool.run(ToolContext(db=session, user=user_b), {"file_id": "f-b"})

    contents = [call.kwargs["content"] for call in remember.await_args_list]
    assert any("conteúdo de a" in c for c in contents)
    assert any("conteúdo de b" in c for c in contents)
    assert provider.calls.count("access-for-rt-a") >= 1
    assert provider.calls.count("access-for-rt-b") >= 1
