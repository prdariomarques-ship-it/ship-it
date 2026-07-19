"""Authentication service layer: registration, login, refresh rotation, logout."""

import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import create_access_token
from auth.password import hash_password, verify_password
from models.user import User, UserRole
from repositories.refresh_token import RefreshTokenRepository
from repositories.user import UserRepository
from utils.config import get_settings


class AuthError(Exception):
    """Domain-level auth failure; routers translate it to HTTP status codes."""

    def __init__(self, message: str, conflict: bool = False) -> None:
        super().__init__(message)
        self.conflict = conflict


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Verified when the email doesn't exist, so a failed login costs the same time
# whether the user exists or not (prevents account enumeration by timing).
_DUMMY_HASH = hash_password("timing-equalizer")


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.settings = get_settings()

    async def register(self, email: str, full_name: str, password: str) -> User:
        if await self.users.get_by_email(email) is not None:
            raise AuthError("Email already registered", conflict=True)
        # Bootstrap: the very first account administers the instance.
        role = UserRole.ADMIN if await self.users.count() == 0 else UserRole.USER
        # PBKDF2 is CPU-bound (~100ms); run it off the event loop.
        hashed = await asyncio.to_thread(hash_password, password)
        return await self.users.create(
            email=email,
            full_name=full_name,
            hashed_password=hashed,
            role=role,
        )

    async def login(self, email: str, password: str) -> tuple[str, str]:
        user = await self.users.get_by_email(email)
        candidate_hash = user.hashed_password if user is not None else _DUMMY_HASH
        valid = await asyncio.to_thread(verify_password, password, candidate_hash)
        if user is None or not valid:
            raise AuthError("Invalid credentials")
        if not user.is_active:
            raise AuthError("User is inactive")
        return await self._issue_pair(user)

    async def refresh(self, refresh_token: str) -> tuple[str, str]:
        """Rotate the refresh token: validate, revoke the old one, issue a new pair."""
        record = await self.refresh_tokens.get_by_hash(
            _hash_refresh_token(refresh_token)
        )
        now = datetime.now(timezone.utc)
        if record is None or record.revoked_at is not None:
            raise AuthError("Invalid refresh token")
        expires_at = record.expires_at
        if expires_at.tzinfo is None:  # SQLite loses tzinfo
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise AuthError("Refresh token expired")

        user = await self.users.get(record.user_id)
        if user is None or not user.is_active:
            raise AuthError("User is inactive")

        await self.refresh_tokens.revoke(record, now)
        return await self._issue_pair(user)

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        """Requires the current password — this is a self-service change for
        an authenticated session, not a "forgot password" recovery flow (that
        would need email delivery, which isn't configured/decided yet; see
        BOOTSTRAP_ADMIN.md for the manual DB-write recovery this replaces for
        the "I still have a session" case)."""
        valid = await asyncio.to_thread(
            verify_password, current_password, user.hashed_password
        )
        if not valid:
            raise AuthError("Current password is incorrect")
        hashed = await asyncio.to_thread(hash_password, new_password)
        await self.users.update(user, hashed_password=hashed)
        # Every other refresh token stops working immediately — a leaked or
        # about-to-be-abandoned password shouldn't keep granting access
        # through a session opened before the change.
        await self.refresh_tokens.revoke_all_for_user(
            user.id, datetime.now(timezone.utc)
        )

    async def logout(self, refresh_token: str) -> None:
        record = await self.refresh_tokens.get_by_hash(
            _hash_refresh_token(refresh_token)
        )
        if record is not None and record.revoked_at is None:
            await self.refresh_tokens.revoke(record, datetime.now(timezone.utc))

    async def _issue_pair(self, user: User) -> tuple[str, str]:
        access_token = create_access_token(str(user.id))
        refresh_token = secrets.token_urlsafe(48)
        # Hygiene: expired tokens are useless; drop them so the table stays small.
        await self.refresh_tokens.purge_expired(user.id, datetime.now(timezone.utc))
        await self.refresh_tokens.create(
            user_id=user.id,
            token_hash=_hash_refresh_token(refresh_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=self.settings.refresh_token_expire_days),
        )
        return access_token, refresh_token
