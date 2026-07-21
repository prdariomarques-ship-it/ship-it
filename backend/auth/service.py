"""Authentication service layer: registration, login, refresh rotation, logout."""

import asyncio
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import create_access_token
from auth.password import hash_password, verify_password
from models.user import User, UserRole
from repositories.password_reset_token import PasswordResetTokenRepository
from repositories.refresh_token import RefreshTokenRepository
from repositories.user import UserRepository
from services.audit import record_log
from utils.config import get_settings


class AuthError(Exception):
    """Domain-level auth failure; routers translate it to HTTP status codes."""

    def __init__(
        self, message: str, conflict: bool = False, forbidden: bool = False
    ) -> None:
        super().__init__(message)
        self.conflict = conflict
        self.forbidden = forbidden


def _hash_token(token: str) -> str:
    """SHA-256 hex digest -- shared by refresh tokens and password-reset
    tokens; only the hash is ever persisted, never the token itself."""
    return hashlib.sha256(token.encode()).hexdigest()


# Verified when the email doesn't exist, so a failed login costs the same time
# whether the user exists or not (prevents account enumeration by timing).
_DUMMY_HASH = hash_password("timing-equalizer")

# request_password_reset has no password hash to equalize against (see
# _DUMMY_HASH above) -- the "found" branch does a couple of extra writes, the
# "not found" branch returns immediately. Same 100ms floor PBKDF2 already
# costs elsewhere in this module, so a timing side-channel here can't
# distinguish "email exists" from "email doesn't" any more finely than a
# failed login already resists.
_PASSWORD_RESET_REQUEST_MIN_SECONDS = 0.1


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.password_reset_tokens = PasswordResetTokenRepository(session)
        self.settings = get_settings()

    async def register(self, email: str, full_name: str, password: str) -> User:
        """Public, unauthenticated registration — bootstrap only.

        Open self-registration on a system that holds shared, non-user-scoped
        data (WhatsApp message history, contacts, church members, store
        customers — see `api/routes.py`) meant anyone who found the login
        page could create an account and immediately read/write all of it.
        Closed after the first account exists; every account after that must
        go through `create_user_as_admin`, gated by `require_admin`.
        """
        if await self.users.count() > 0:
            raise AuthError(
                "Public registration is closed; ask an administrator to "
                "create your account",
                forbidden=True,
            )
        if await self.users.get_by_email(email) is not None:
            raise AuthError("Email already registered", conflict=True)
        # PBKDF2 is CPU-bound (~100ms); run it off the event loop.
        hashed = await asyncio.to_thread(hash_password, password)
        return await self.users.create(
            email=email,
            full_name=full_name,
            hashed_password=hashed,
            role=UserRole.ADMIN,  # the bootstrap account always administers the instance
        )

    async def create_user_as_admin(
        self,
        email: str,
        full_name: str,
        password: str,
        role: UserRole = UserRole.USER,
    ) -> User:
        """Admin-only user creation — the only way to add an account once
        the bootstrap admin exists (see `register`). Callers must enforce
        `require_admin` themselves; this method has no role check of its
        own, matching every other service method's convention of trusting
        the router's dependency to have already gated access."""
        if await self.users.get_by_email(email) is not None:
            raise AuthError("Email already registered", conflict=True)
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
            _hash_token(refresh_token)
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
        an authenticated session. For the "I have no session and no password"
        case, see `request_password_reset`/`reset_password`."""
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

    async def request_password_reset(self, email: str) -> None:
        """"Forgot password" recovery. No email/SMS delivery is configured
        for this project (no SMTP, no phone linked to `User`), so there is no
        automated out-of-band channel this project can deliver a token
        through yet.

        The token itself is deliberately never surfaced by this method (not
        logged, not returned) -- only `admin_generate_reset_token` (below)
        ever hands back a raw token, to an already-authenticated admin, who
        relays it to the requester manually (WhatsApp, verbally, etc.,
        outside this system). This method's job is only to (a) invalidate
        any stale pending token and (b) leave an audit trail an admin can
        notice, never to hand out a usable credential itself.

        Always succeeds from the caller's point of view regardless of
        whether the email matches an account, both in response shape (always
        returns normally) and in timing (a floor keeps the "not found" branch
        from returning measurably faster than the "found" one -- see
        `_PASSWORD_RESET_REQUEST_MIN_SECONDS`)."""
        start = time.monotonic()
        user = await self.users.get_by_email(email)
        if user is not None:
            now = datetime.now(timezone.utc)
            await self.password_reset_tokens.invalidate_unused_for_user(user.id, now)
            await self.password_reset_tokens.purge_expired(user.id, now)
            await record_log(
                self.users.session,
                source=f"auth:password_reset:{user.id}",
                message=f"Password reset requested for user {user.id}",
                level="warning",
            )
        elapsed = time.monotonic() - start
        if elapsed < _PASSWORD_RESET_REQUEST_MIN_SECONDS:
            await asyncio.sleep(_PASSWORD_RESET_REQUEST_MIN_SECONDS - elapsed)

    async def admin_generate_reset_token(self, user_id: int) -> str:
        """Admin-only (callers must enforce `require_admin`, same convention
        as `create_user_as_admin`). Issues a fresh reset token for `user_id`,
        invalidating any token already pending for that user, and returns the
        raw value exactly once -- it is never persisted or logged in plain
        text, only its hash is. The admin is expected to relay it to the user
        through whatever channel they judge appropriate."""
        user = await self.users.get(user_id)
        if user is None:
            raise AuthError("User not found")
        now = datetime.now(timezone.utc)
        await self.password_reset_tokens.invalidate_unused_for_user(user.id, now)
        await self.password_reset_tokens.purge_expired(user.id, now)
        token = secrets.token_urlsafe(32)
        await self.password_reset_tokens.create(
            user_id=user.id,
            token_hash=_hash_token(token),
            expires_at=now
            + timedelta(minutes=self.settings.password_reset_token_expire_minutes),
        )
        await record_log(
            self.users.session,
            source=f"auth:password_reset:{user.id}",
            message=f"Admin generated a password reset token for user {user.id}",
            level="warning",
        )
        return token

    async def reset_password(self, token: str, new_password: str) -> None:
        record = await self.password_reset_tokens.get_by_hash(_hash_token(token))
        now = datetime.now(timezone.utc)
        if record is None or record.used_at is not None:
            raise AuthError("Invalid or expired reset token")
        expires_at = record.expires_at
        if expires_at.tzinfo is None:  # SQLite loses tzinfo
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise AuthError("Invalid or expired reset token")

        user = await self.users.get(record.user_id)
        if user is None:
            raise AuthError("Invalid or expired reset token")

        hashed = await asyncio.to_thread(hash_password, new_password)
        await self.users.update(user, hashed_password=hashed)
        await self.password_reset_tokens.mark_used(record, now)
        # Same as change_password: a password reset invalidates every
        # existing session, not just the one (if any) doing the resetting.
        await self.refresh_tokens.revoke_all_for_user(user.id, now)
        await record_log(
            self.users.session,
            source=f"auth:password_reset:{user.id}",
            message=f"Password reset completed for user {user.id}",
            level="warning",
        )

    async def logout(self, refresh_token: str) -> None:
        record = await self.refresh_tokens.get_by_hash(
            _hash_token(refresh_token)
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
            token_hash=_hash_token(refresh_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=self.settings.refresh_token_expire_days),
        )
        return access_token, refresh_token
