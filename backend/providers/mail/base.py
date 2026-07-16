"""Provider-agnostic mail contract (Strategy pattern) — Sprint 1: Gmail only,
but shaped so a second provider (e.g. Outlook/Microsoft Graph, generic IMAP)
is a new class + a factory entry, never a change to callers. Same pattern
already used for LLM and WhatsApp providers.

A Provider's job is translation and transport only: turn its vendor's API
shape into `EmailMessage`/`EmailThread`, and turn a search request into
whatever query syntax the vendor expects. No business logic, no database
access, no LLM calls — those belong to `agents/tools/mail.py` and `mail/`.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class MailProviderError(RuntimeError):
    pass


class EmailMessage(BaseModel):
    """A single message, normalized across providers — the only shape the
    rest of the application (tools, agents) ever sees."""

    id: str
    thread_id: str
    sender: str
    to: list[str] = []
    subject: str = ""
    snippet: str = ""
    body: str = ""
    date: datetime | None = None
    labels: list[str] = []


class EmailThread(BaseModel):
    id: str
    subject: str = ""
    messages: list[EmailMessage] = []


class EmailSearchQuery(BaseModel):
    """Every field is optional and additive (AND semantics) — matches the
    Sprint 1 scope: remetente, assunto, período, palavras-chave, etiquetas."""

    sender: str | None = None
    subject: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    keywords: str | None = None
    labels: list[str] = []
    limit: int = 20


class OAuthTokens(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int = 3600
    scope: str = ""


class MailProvider(ABC):
    """Strategy interface implemented by every mail integration."""

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
    async def search(
        self, access_token: str, query: EmailSearchQuery
    ) -> list[EmailMessage]:
        """Search messages in the authorized mailbox."""

    @abstractmethod
    async def get_thread(self, access_token: str, thread_id: str) -> EmailThread:
        """Fetch a full thread (all messages), oldest first."""
