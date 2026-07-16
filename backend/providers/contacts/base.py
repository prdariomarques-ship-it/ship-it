"""Provider-agnostic Google Contacts contract (Strategy pattern) — Sprint 2:
Google (People API) only, same shape as `providers/mail/base.py` and
`providers/calendar/base.py` so a second provider is a new class + a
factory entry, never a change to callers.

A Provider's job is translation and transport only. No business logic, no
database access — those belong to `agents/tools/gcontacts.py` and
`gcontacts/`.

`Contact` here is a remote Google Contacts (People API) entry — deliberately
not named the same as `models.contact.Contact`, which is Dario OS's own
WhatsApp-conversation contact book and has nothing to do with this
integration. See `docs/CONTACTS.md`.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class ContactsProviderError(RuntimeError):
    pass


class Contact(BaseModel):
    """A single Google Contacts entry, normalized across providers."""

    resource_name: str
    etag: str = ""
    display_name: str = ""
    given_name: str = ""
    family_name: str = ""
    emails: list[str] = []
    phones: list[str] = []


class ContactSearchQuery(BaseModel):
    query: str | None = None
    limit: int = 50


class NewContact(BaseModel):
    given_name: str
    family_name: str = ""
    emails: list[str] = []
    phones: list[str] = []


class ContactUpdate(BaseModel):
    given_name: str | None = None
    family_name: str | None = None
    emails: list[str] | None = None
    phones: list[str] | None = None


class OAuthTokens(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int = 3600
    scope: str = ""


class ContactsProvider(ABC):
    """Strategy interface implemented by every contacts integration."""

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
    async def search_contacts(
        self, access_token: str, query: ContactSearchQuery
    ) -> list[Contact]:
        """List/search contacts (covers "listar", "buscar", "localizar
        telefone/e-mail" — a name/phone/email query filters client-side over
        the full address book, which is small enough for a personal
        instance that this beats the People API's separate, eventually-
        consistent search-index endpoint)."""

    @abstractmethod
    async def get_contact(self, access_token: str, resource_name: str) -> Contact:
        """Fetch one contact (needed before update: the People API requires
        the current etag for optimistic-concurrency updates)."""

    @abstractmethod
    async def create_contact(self, access_token: str, contact: NewContact) -> Contact:
        """Create a new contact."""

    @abstractmethod
    async def update_contact(
        self, access_token: str, resource_name: str, update: ContactUpdate
    ) -> Contact:
        """Patch an existing contact (only the provided fields change)."""

    @abstractmethod
    async def delete_contact(self, access_token: str, resource_name: str) -> None:
        """Delete a contact."""
