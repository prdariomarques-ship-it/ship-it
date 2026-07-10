"""Google Drive tools — Sprint 3, the "base de conhecimento" domain. List,
search, read (PDF/DOCX/TXT/Markdown/CSV), index, index a folder, summarize,
and refresh the index — nothing else (no upload/edit/delete on Drive; no
Google Docs/Sheets/Slides, out of scope by design).

Registered only on `agents/assistant_agent.py`. No other agent gets these —
same single-gateway principle as Email/Calendar/Contacts. A specialized
agent that needs something from indexed knowledge reaches it through the
existing `search_memory` tool (already registered on `assistant`) or a
Cognitive Planner multi-step plan, never through direct tool access — see
`docs/DRIVE.md`.

**Indexing writes exclusively to the existing Memory Manager / Knowledge
Store (Qdrant, `source="knowledge"`)** — no new database, no parallel
knowledge mechanism. `GoogleDriveIndexedFile` (`models/gdrive_indexed_file.py`)
is bookkeeping only (which file, when, which `Embedding.id`s) — it never
holds document content; the content itself lives only in the same Qdrant
collection every other memory already uses.
"""
from datetime import datetime, timezone

from agents.tools.base import Tool, ToolContext, ok
from memory.manager import KNOWLEDGE_SOURCE, memory_manager
from providers.drive.base import DriveFile, DriveProviderError, DriveSearchQuery
from providers.drive.factory import get_drive_provider
from providers.llm.base import ChatMessage
from providers.llm.factory import get_llm_provider
from repositories.gdrive_account import GoogleDriveAccountRepository
from repositories.gdrive_indexed_file import GoogleDriveIndexedFileRepository
from services.token_crypto import TokenEncryptionNotConfigured, decrypt_token


class DriveNotConnectedError(RuntimeError):
    """No Google Drive authorized for this user — surfaced to the model as
    a normal tool error (via Tool.run's catch-all), same as any other tool
    failure. Never a crash, never a fallback to someone else's Drive."""


async def _get_access_token(context: ToolContext) -> str:
    """The only place a Drive account is chosen — always from
    `context.user.id` (set by the application, never by the model). Same
    principle as `agents/tools/mail.py`/`gcalendar.py`/`gcontacts.py`."""
    if context.user is None:
        raise DriveNotConnectedError("No authenticated user in context")

    provider = get_drive_provider()
    account = await GoogleDriveAccountRepository(context.db).get_by_user(context.user.id, provider.name)
    if account is None:
        raise DriveNotConnectedError(
            "Nenhum Google Drive conectado. Peça ao administrador para conectar em /api/gdrive/connect."
        )
    try:
        refresh_token = decrypt_token(account.encrypted_refresh_token)
    except TokenEncryptionNotConfigured as exc:
        raise DriveNotConnectedError(str(exc)) from exc

    try:
        tokens = await provider.refresh_access_token(refresh_token)
    except DriveProviderError as exc:
        raise DriveNotConnectedError(
            "A conexão com o Google Drive expirou ou foi revogada. Peça ao administrador para "
            "reconectar em /api/gdrive/connect."
        ) from exc
    return tokens.access_token


def _file_to_dict(file: DriveFile) -> dict:
    return {
        "id": file.id,
        "name": file.name,
        "mime_type": file.mime_type,
        "size": file.size,
        "modified_time": file.modified_time,
        "parents": file.parents,
        "web_view_link": file.web_view_link,
    }


_MAX_CONTENT_CHARS = 8000  # keep a long document from blowing out the conversation context
_CHUNK_SIZE = 1500
_MAX_CHUNKS_PER_FILE = 30  # ~45k chars cap per file indexed into the Knowledge Store


def _chunk_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks = [text[i : i + _CHUNK_SIZE] for i in range(0, len(text), _CHUNK_SIZE)]
    return chunks[:_MAX_CHUNKS_PER_FILE]


def _up_to_date(stored_modified_time: datetime, current_modified_time: datetime) -> bool:
    """SQLite (local dev/tests) doesn't round-trip tzinfo through a
    `DateTime(timezone=True)` column the way Postgres does — a value read
    back can come back naive even though it was written as UTC-aware,
    which raises `TypeError` on direct comparison. Normalize both sides to
    UTC before comparing rather than assuming either backend's behavior."""
    if stored_modified_time.tzinfo is None:
        stored_modified_time = stored_modified_time.replace(tzinfo=timezone.utc)
    if current_modified_time.tzinfo is None:
        current_modified_time = current_modified_time.replace(tzinfo=timezone.utc)
    return stored_modified_time >= current_modified_time


def _citation(file_name: str, modified_time, part: int, total: int) -> str:
    when = modified_time.isoformat() if modified_time else "data desconhecida"
    return f"[Google Drive: {file_name} | atualizado em {when} | parte {part}/{total}]\n\n"


async def _list_files(context: ToolContext, folder_id: str | None = None, limit: int = 20) -> str:
    access_token = await _get_access_token(context)
    provider = get_drive_provider()
    try:
        files = await provider.list_files(access_token, folder_id=folder_id, limit=min(limit, 50))
    except DriveProviderError as exc:
        raise RuntimeError(f"Falha ao listar arquivos: {exc}") from exc
    return ok(files=[_file_to_dict(f) for f in files])


async def _search_files(
    context: ToolContext,
    name: str | None = None,
    mime_type: str | None = None,
    folder_id: str | None = None,
    query: str | None = None,
    limit: int = 20,
) -> str:
    access_token = await _get_access_token(context)
    provider = get_drive_provider()
    search = DriveSearchQuery(name=name, mime_type=mime_type, folder_id=folder_id, query=query, limit=min(limit, 50))
    try:
        files = await provider.search_files(access_token, search)
    except DriveProviderError as exc:
        raise RuntimeError(f"Falha ao buscar arquivos: {exc}") from exc
    return ok(files=[_file_to_dict(f) for f in files])


async def _read_file(context: ToolContext, file_id: str) -> str:
    access_token = await _get_access_token(context)
    provider = get_drive_provider()
    try:
        metadata = await provider.get_metadata(access_token, file_id)
        text = await provider.read_file_text(access_token, file_id)
    except DriveProviderError as exc:
        raise RuntimeError(f"Falha ao ler o arquivo: {exc}") from exc
    return ok(
        file_id=file_id,
        file_name=metadata.name,
        mime_type=metadata.mime_type,
        content=text[:_MAX_CONTENT_CHARS],
        truncated=len(text) > _MAX_CONTENT_CHARS,
    )


async def _index_one(context: ToolContext, provider, access_token: str, file_id: str) -> dict:
    """Shared by `index_google_drive_file` and `index_google_drive_folder`
    — reads, chunks, embeds into the Knowledge Store, and records
    bookkeeping. Skips a file that hasn't changed since it was last
    indexed; replaces (never accumulates) a changed file's chunks."""
    metadata = await provider.get_metadata(access_token, file_id)
    repository = GoogleDriveIndexedFileRepository(context.db)
    existing = await repository.get_by_user_and_file(context.user.id, file_id)
    if existing is not None and metadata.modified_time and _up_to_date(existing.modified_time, metadata.modified_time):
        return {"file_id": file_id, "file_name": metadata.name, "indexed": False, "reason": "sem alterações desde a última indexação"}

    # Captured before the slow part (download + chunk + embed) so we can
    # detect, right before writing, whether a concurrent call for this same
    # file already finished in the meantime.
    existing_indexed_at = existing.indexed_at if existing is not None else None

    text = await provider.read_file_text(access_token, file_id)
    chunks = _chunk_text(text)
    if not chunks:
        return {"file_id": file_id, "file_name": metadata.name, "indexed": False, "reason": "arquivo vazio"}

    if existing is not None and existing.embedding_ids:
        await memory_manager.forget(context.db, existing.embedding_ids)

    embedding_ids = []
    for index, chunk in enumerate(chunks, start=1):
        content = _citation(metadata.name, metadata.modified_time, index, len(chunks)) + chunk
        embedding_id = await memory_manager.remember(context.db, content=content, source=KNOWLEDGE_SOURCE)
        embedding_ids.append(embedding_id)

    # Race guard: if another concurrent call for this same file already
    # committed a newer result while we were downloading/chunking/embedding,
    # blindly overwriting it here would permanently orphan the chunks we
    # just created — never referenced by the bookkeeping row, never cleaned
    # up by a future reindex (which only forgets whatever the row currently
    # points to). Self-clean instead of winning the write.
    current = await repository.get_by_user_and_file(context.user.id, file_id)
    if current is not None and current.indexed_at != existing_indexed_at:
        await memory_manager.forget(context.db, embedding_ids)
        return {
            "file_id": file_id,
            "file_name": metadata.name,
            "indexed": False,
            "reason": "atualizado por outra indexação concorrente",
        }

    await repository.upsert_for_user_and_file(
        context.user.id,
        file_id,
        file_name=metadata.name,
        mime_type=metadata.mime_type,
        modified_time=metadata.modified_time or datetime.now(timezone.utc),
        embedding_ids=embedding_ids,
        indexed_at=datetime.now(timezone.utc),
    )
    return {"file_id": file_id, "file_name": metadata.name, "indexed": True, "chunks": len(chunks)}


async def _index_file(context: ToolContext, file_id: str) -> str:
    access_token = await _get_access_token(context)
    provider = get_drive_provider()
    try:
        result = await _index_one(context, provider, access_token, file_id)
    except DriveProviderError as exc:
        raise RuntimeError(f"Falha ao indexar o arquivo: {exc}") from exc
    return ok(**result)


_MAX_FILES_PER_FOLDER_INDEX = 20  # bounded per call — same convention as every list/search limit elsewhere


async def _index_folder(context: ToolContext, folder_id: str, limit: int = 20) -> str:
    access_token = await _get_access_token(context)
    provider = get_drive_provider()
    try:
        files = await provider.search_files(
            access_token, DriveSearchQuery(folder_id=folder_id, limit=min(limit, _MAX_FILES_PER_FOLDER_INDEX))
        )
    except DriveProviderError as exc:
        raise RuntimeError(f"Falha ao listar a pasta: {exc}") from exc

    indexed, skipped, failed = [], [], []
    for file in files:
        try:
            result = await _index_one(context, provider, access_token, file.id)
        except DriveProviderError as exc:
            failed.append({"file_id": file.id, "file_name": file.name, "error": str(exc)})
            continue
        (indexed if result["indexed"] else skipped).append(result)

    return ok(indexed=indexed, skipped=skipped, failed=failed)


_MAX_FILES_PER_INDEX_UPDATE = 50


async def _update_index(context: ToolContext, limit: int = 20) -> str:
    """Re-checks previously indexed files (oldest-indexed first) and
    re-indexes any whose Drive `modifiedTime` moved since last time —
    "atualizar índice"."""
    access_token = await _get_access_token(context)
    provider = get_drive_provider()
    repository = GoogleDriveIndexedFileRepository(context.db)
    tracked = await repository.list_by_user(context.user.id, limit=min(limit, _MAX_FILES_PER_INDEX_UPDATE))

    updated, unchanged, failed = [], [], []
    for entry in tracked:
        try:
            result = await _index_one(context, provider, access_token, entry.file_id)
        except DriveProviderError as exc:
            failed.append({"file_id": entry.file_id, "file_name": entry.file_name, "error": str(exc)})
            continue
        (updated if result["indexed"] else unchanged).append(result)

    return ok(updated=updated, unchanged=unchanged, failed=failed, checked=len(tracked))


_SUMMARY_PROMPT = (
    "Você resume um documento do Google Drive para o Dario OS. Leia o conteúdo abaixo e escreva um "
    "resumo conciso (no máximo 8 frases) dos pontos principais. Responda apenas com o resumo, em "
    "português brasileiro."
)


async def _summarize_document(context: ToolContext, file_id: str) -> str:
    access_token = await _get_access_token(context)
    provider = get_drive_provider()
    try:
        metadata = await provider.get_metadata(access_token, file_id)
        text = await provider.read_file_text(access_token, file_id)
    except DriveProviderError as exc:
        raise RuntimeError(f"Falha ao ler o arquivo: {exc}") from exc

    if not text.strip():
        return ok(summary="", file_name=metadata.name)

    result = await get_llm_provider().chat(
        [
            ChatMessage(role="system", content=_SUMMARY_PROMPT),
            ChatMessage(role="user", content=f"Arquivo: {metadata.name}\n\n{text[:_MAX_CONTENT_CHARS]}"),
        ]
    )
    return ok(summary=result.content.strip(), file_name=metadata.name)


list_google_drive_files_tool = Tool(
    name="list_google_drive_files",
    description="Lista arquivos do Google Drive conectado, opcionalmente dentro de uma pasta.",
    handler=_list_files,
    parameters={
        "type": "object",
        "properties": {
            "folder_id": {"type": "string", "description": "Id da pasta a listar (padrão: raiz/todos)"},
            "limit": {"type": "integer", "description": "Máximo de resultados (padrão 20)"},
        },
        "required": [],
    },
)

search_google_drive_files_tool = Tool(
    name="search_google_drive_files",
    description=(
        "Busca arquivos do Google Drive por nome, tipo, pasta e/ou texto livre. Use para 'procure o "
        "contrato da Oficina das Tintas' (name/query), 'arquivos PDF' (mime_type) ou 'arquivos na "
        "pasta X' (folder_id)."
    ),
    handler=_search_files,
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Parte do nome do arquivo"},
            "mime_type": {"type": "string", "description": "Ex: application/pdf"},
            "folder_id": {"type": "string", "description": "Restringir a uma pasta"},
            "query": {"type": "string", "description": "Palavras-chave no conteúdo do arquivo"},
            "limit": {"type": "integer", "description": "Máximo de resultados (padrão 20)"},
        },
        "required": [],
    },
)

read_google_drive_file_tool = Tool(
    name="read_google_drive_file",
    description="Lê o conteúdo de um arquivo do Google Drive (PDF, DOCX, TXT, Markdown ou CSV).",
    handler=_read_file,
    parameters={
        "type": "object",
        "properties": {"file_id": {"type": "string"}},
        "required": ["file_id"],
    },
)

index_google_drive_file_tool = Tool(
    name="index_google_drive_file",
    description=(
        "Lê um arquivo do Google Drive e adiciona seu conteúdo à base de conhecimento permanente "
        "(pesquisável depois via a ferramenta search_memory). Pula arquivos sem alteração desde a "
        "última indexação."
    ),
    handler=_index_file,
    parameters={
        "type": "object",
        "properties": {"file_id": {"type": "string"}},
        "required": ["file_id"],
    },
)

index_google_drive_folder_tool = Tool(
    name="index_google_drive_folder",
    description=(
        "Indexa todos os arquivos suportados de uma pasta do Google Drive na base de conhecimento "
        f"(até {_MAX_FILES_PER_FOLDER_INDEX} arquivos por chamada)."
    ),
    handler=_index_folder,
    parameters={
        "type": "object",
        "properties": {
            "folder_id": {"type": "string"},
            "limit": {"type": "integer", "description": f"Máximo de arquivos (padrão 20, até {_MAX_FILES_PER_FOLDER_INDEX})"},
        },
        "required": ["folder_id"],
    },
)

summarize_google_drive_document_tool = Tool(
    name="summarize_google_drive_document",
    description="Resume um documento do Google Drive em poucas frases.",
    handler=_summarize_document,
    parameters={
        "type": "object",
        "properties": {"file_id": {"type": "string"}},
        "required": ["file_id"],
    },
)

update_google_drive_index_tool = Tool(
    name="update_google_drive_index",
    description=(
        "Verifica os arquivos já indexados e reindexa os que mudaram no Google Drive desde a última "
        "vez ('o que mudou na última versão'). Não recebe pasta — atualiza a base de conhecimento já "
        "existente inteira, em lotes."
    ),
    handler=_update_index,
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": f"Máximo de arquivos a checar (padrão 20, até {_MAX_FILES_PER_INDEX_UPDATE})"}
        },
        "required": [],
    },
)
