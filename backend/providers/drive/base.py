"""Provider-agnostic Google Drive contract (Strategy pattern) — Sprint 3:
Google only, same shape as `providers/mail/base.py`, `providers/calendar/base.py`
and `providers/contacts/base.py` so a second provider (e.g. Dropbox, a
generic WebDAV store) is a new class + a factory entry, never a change to
callers.

A Provider's job is translation and transport only — including, here, the
byte-level parsing of a downloaded file into readable text (same category
of work as `GmailProvider._extract_body` decoding a MIME payload; parsing
bytes is translation, not business logic). No database access, no LLM
calls, no writes to the knowledge store — those belong to
`agents/tools/gdrive.py`.

`DriveFile` is deliberately unrelated to any Dario OS model — this domain
has no internal counterpart to collide with (unlike the calendar/contacts
domains), but keeps the `Drive`-prefixed naming for consistency with
`gcalendar`/`gcontacts`. See `docs/DRIVE.md`.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class DriveProviderError(RuntimeError):
    pass


class UnsupportedDriveFileTypeError(DriveProviderError):
    """The file's type isn't one Sprint 3 reads (only PDF, DOCX, TXT, MD,
    CSV — explicitly not Google Docs/Sheets/Slides, out of scope)."""


class DriveFileTooLargeError(DriveProviderError):
    """The file exceeds `GDRIVE_MAX_FILE_SIZE_BYTES` — refused before
    download, never partially read into memory."""


class DriveFile(BaseModel):
    id: str
    name: str
    mime_type: str = ""
    size: int = 0
    modified_time: datetime | None = None
    parents: list[str] = []
    web_view_link: str = ""


class DriveSearchQuery(BaseModel):
    """Every field is optional and additive (AND semantics) — matches the
    Sprint 3 scope: nome, pasta, tipo, texto livre."""

    name: str | None = None
    folder_id: str | None = None
    mime_type: str | None = None
    query: str | None = None
    limit: int = 20


class OAuthTokens(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int = 3600
    scope: str = ""


class DriveProvider(ABC):
    """Strategy interface implemented by every Drive integration."""

    name: str

    @abstractmethod
    def authorization_url(self, state: str) -> str:
        """Build the URL the browser is redirected to for consent."""

    @abstractmethod
    async def exchange_code(self, code: str) -> OAuthTokens:
        """Exchange an OAuth authorization code for tokens (first connect)."""

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """Exchange a stored refresh token for a fresh access token."""

    @abstractmethod
    async def list_files(
        self, access_token: str, folder_id: str | None = None, limit: int = 20
    ) -> list[DriveFile]:
        """List files, optionally scoped to one folder."""

    @abstractmethod
    async def search_files(
        self, access_token: str, query: DriveSearchQuery
    ) -> list[DriveFile]:
        """Search files by name/folder/type/free text (covers every
        "buscar..." bullet in the Sprint 3 spec via parameters)."""

    @abstractmethod
    async def get_metadata(self, access_token: str, file_id: str) -> DriveFile:
        """Fetch one file's metadata."""

    @abstractmethod
    async def read_file_text(self, access_token: str, file_id: str) -> str:
        """Download (size-capped) and extract readable text — PDF, DOCX,
        TXT, Markdown, CSV. Raises `UnsupportedDriveFileTypeError` for any
        other type (including native Google Docs/Sheets/Slides — out of
        scope by design) and `DriveFileTooLargeError` before downloading
        anything over the configured size cap."""
