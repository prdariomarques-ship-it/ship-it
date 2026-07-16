"""Google Drive provider — REST via httpx, no new SDK dependency (same
choice already made for Gmail/Calendar/Contacts). Byte-level text
extraction uses two small, pure-Python libraries (`pypdf`, `python-docx`) —
new dependencies, but for a declared feature (reading PDF/DOCX), not a new
architecture; same category of addition as `cryptography` in Sprint 1.

Docs: https://developers.google.com/drive/api/v3/reference/files
"""

import csv
import io
from datetime import datetime
from urllib.parse import quote, urlencode

import httpx
from docx import Document as DocxDocument
from pypdf import PdfReader

from providers.drive.base import (
    DriveFile,
    DriveFileTooLargeError,
    DriveProvider,
    DriveProviderError,
    DriveSearchQuery,
    OAuthTokens,
    UnsupportedDriveFileTypeError,
)
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

# Read-only by design (Sprint 3 scope: list, search, read, index — never
# upload/edit/delete a Drive file).
GOOGLE_DRIVE_SCOPES = "https://www.googleapis.com/auth/drive.readonly"

_FILE_FIELDS = "id,name,mimeType,size,modifiedTime,parents,webViewLink"
_LIST_FIELDS = f"files({_FILE_FIELDS})"

# Native Google Workspace formats have no downloadable bytes via alt=media
# (they'd need files.export to a target mimeType) — reading them is exactly
# the Google Docs/Sheets/Slides integration this sprint explicitly excludes.
_GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."

_SUPPORTED_TEXT_MIME_TYPES = {"text/plain", "text/markdown", "text/csv"}
_DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_PDF_MIME_TYPE = "application/pdf"
_TEXT_EXTENSIONS = {".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv"}


class GoogleDriveProvider(DriveProvider):
    name = "google"

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = settings.google_client_id
        self._client_secret = settings.google_client_secret
        self._redirect_uri = settings.google_drive_redirect_uri
        self._oauth_base_url = settings.google_oauth_base_url
        self._token_url = settings.google_token_url
        self._api_base_url = settings.google_drive_api_base_url.rstrip("/")
        self._max_file_size_bytes = settings.gdrive_max_file_size_bytes

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_DRIVE_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{self._oauth_base_url}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OAuthTokens:
        return await self._token_request(
            {
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
            }
        )

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        result = await self._token_request(
            {
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            }
        )
        return result.model_copy(update={"refresh_token": refresh_token})

    async def _token_request(self, data: dict) -> OAuthTokens:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self._token_url, data=data)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Google Drive OAuth token request failed: %s", exc)
            raise DriveProviderError(
                f"Google Drive OAuth token request failed: {exc}"
            ) from exc
        body = response.json()
        return OAuthTokens(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_in=body.get("expires_in", 3600),
            scope=body.get("scope", ""),
        )

    def _headers(self, access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}

    async def _get_json(
        self, access_token: str, path: str, params: dict | None = None
    ) -> dict:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self._api_base_url}{path}",
                    headers=self._headers(access_token),
                    params=params,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Google Drive API request failed (%s): %s", path, exc)
            raise DriveProviderError(f"Google Drive API request failed: {exc}") from exc
        return response.json()

    async def _get_bytes(
        self, access_token: str, path: str, params: dict | None = None
    ) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(
                    f"{self._api_base_url}{path}",
                    headers=self._headers(access_token),
                    params=params,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Google Drive download failed (%s): %s", path, exc)
            raise DriveProviderError(f"Google Drive download failed: {exc}") from exc
        return response.content

    async def list_files(
        self, access_token: str, folder_id: str | None = None, limit: int = 20
    ) -> list[DriveFile]:
        return await self.search_files(
            access_token, DriveSearchQuery(folder_id=folder_id, limit=limit)
        )

    async def search_files(
        self, access_token: str, query: DriveSearchQuery
    ) -> list[DriveFile]:
        params = {
            "q": _build_query(query),
            "fields": _LIST_FIELDS,
            "pageSize": query.limit,
        }
        result = await self._get_json(access_token, "/files", params=params)
        return [_parse_file(raw) for raw in result.get("files", [])]

    async def get_metadata(self, access_token: str, file_id: str) -> DriveFile:
        raw = await self._get_json(
            access_token,
            f"/files/{quote(file_id, safe='')}",
            params={"fields": _FILE_FIELDS},
        )
        return _parse_file(raw)

    async def read_file_text(self, access_token: str, file_id: str) -> str:
        metadata = await self.get_metadata(access_token, file_id)
        mime_type = _resolve_mime_type(metadata)

        if mime_type.startswith(_GOOGLE_NATIVE_PREFIX):
            raise UnsupportedDriveFileTypeError(
                f"'{metadata.name}' é um arquivo nativo do Google ({mime_type}) — Google Docs/Sheets/"
                "Slides não fazem parte do escopo desta integração."
            )
        if mime_type not in _SUPPORTED_TEXT_MIME_TYPES and mime_type not in (
            _PDF_MIME_TYPE,
            _DOCX_MIME_TYPE,
        ):
            raise UnsupportedDriveFileTypeError(
                f"'{metadata.name}' tem um tipo não suportado ({mime_type}) — apenas PDF, DOCX, TXT, "
                "Markdown e CSV são lidos nesta sprint."
            )
        if metadata.size > self._max_file_size_bytes:
            raise DriveFileTooLargeError(
                f"'{metadata.name}' ({metadata.size} bytes) excede o limite de "
                f"{self._max_file_size_bytes} bytes para download."
            )

        raw_bytes = await self._get_bytes(
            access_token, f"/files/{quote(file_id, safe='')}", params={"alt": "media"}
        )
        return _extract_text(mime_type, raw_bytes)


def _build_query(query: DriveSearchQuery) -> str:
    """Drive's own search operators — translating the normalized query into
    vendor syntax is exactly the kind of translation-only work that belongs
    in a Provider (same principle as `providers/mail/gmail/provider.py::_build_search_query`)."""
    parts = ["trashed = false"]
    if query.name:
        escaped = query.name.replace("'", "\\'")
        parts.append(f"name contains '{escaped}'")
    if query.folder_id:
        escaped = query.folder_id.replace("'", "\\'")
        parts.append(f"'{escaped}' in parents")
    if query.mime_type:
        escaped = query.mime_type.replace("'", "\\'")
        parts.append(f"mimeType = '{escaped}'")
    if query.query:
        escaped = query.query.replace("'", "\\'")
        parts.append(f"fullText contains '{escaped}'")
    return " and ".join(parts)


def _parse_file(raw: dict) -> DriveFile:
    modified = None
    if raw.get("modifiedTime"):
        modified = datetime.fromisoformat(raw["modifiedTime"].replace("Z", "+00:00"))
    size = 0
    if raw.get("size"):
        try:
            size = int(raw["size"])
        except (TypeError, ValueError):
            size = 0
    return DriveFile(
        id=raw["id"],
        name=raw.get("name", ""),
        mime_type=raw.get("mimeType", ""),
        size=size,
        modified_time=modified,
        parents=raw.get("parents", []) or [],
        web_view_link=raw.get("webViewLink", ""),
    )


def _resolve_mime_type(metadata: DriveFile) -> str:
    """Drive sometimes reports a generic mimeType for plain-text-ish files;
    fall back to the file extension when the reported type isn't one we
    recognize, so a `.md` uploaded as `text/plain` still reads as Markdown."""
    if metadata.mime_type in _SUPPORTED_TEXT_MIME_TYPES or metadata.mime_type in (
        _PDF_MIME_TYPE,
        _DOCX_MIME_TYPE,
    ):
        return metadata.mime_type
    for extension, mime_type in _TEXT_EXTENSIONS.items():
        if metadata.name.lower().endswith(extension):
            return mime_type
    return metadata.mime_type


def _extract_text(mime_type: str, raw_bytes: bytes) -> str:
    if mime_type == _PDF_MIME_TYPE:
        return _extract_pdf_text(raw_bytes)
    if mime_type == _DOCX_MIME_TYPE:
        return _extract_docx_text(raw_bytes)
    if mime_type == "text/csv":
        return _extract_csv_text(raw_bytes)
    # text/plain, text/markdown
    return raw_bytes.decode("utf-8", errors="replace")


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # noqa: BLE001 - any malformed-PDF error becomes a clean provider error
        raise DriveProviderError(f"Falha ao ler PDF: {exc}") from exc


def _extract_docx_text(raw_bytes: bytes) -> str:
    try:
        document = DocxDocument(io.BytesIO(raw_bytes))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except Exception as exc:  # noqa: BLE001 - any malformed-DOCX error becomes a clean provider error
        raise DriveProviderError(f"Falha ao ler DOCX: {exc}") from exc


def _extract_csv_text(raw_bytes: bytes) -> str:
    try:
        text = raw_bytes.decode("utf-8", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))
        return "\n".join(", ".join(row) for row in rows)
    except Exception as exc:  # noqa: BLE001 - any malformed-CSV error becomes a clean provider error
        raise DriveProviderError(f"Falha ao ler CSV: {exc}") from exc
