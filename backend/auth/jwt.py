"""JWT creation and validation."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as pyjwt

from utils.config import get_settings

# Claim that marks a token as scoped (limited), as opposed to a full-access
# token. See auth/scopes.py for what a scope is allowed to do.
SCOPE_CLAIM = "scope"


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes
        if expires_minutes is not None
        else settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire, "iat": datetime.now(timezone.utc)}
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_scoped_access_token(subject: str, scope: str, expires_days: int) -> str:
    """Long-lived token limited to `scope` (enforced in `auth/scopes.py`).

    TTL is validated against `scoped_token_max_days`: a scoped token is meant
    for an integration, not a person, so it must expire, but not every 30
    minutes like an interactive session. Carries a `jti` for audit trails.
    """
    settings = get_settings()
    if not scope:
        raise ValueError("scope must not be empty")
    if expires_days < 1 or expires_days > settings.scoped_token_max_days:
        raise ValueError(
            f"expires_days must be between 1 and {settings.scoped_token_max_days}"
        )
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        SCOPE_CLAIM: scope,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(days=expires_days),
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_claims(token: str) -> dict[str, Any] | None:
    """Return the verified claims of an access token (full-access or scoped).

    None when the signature/expiry is invalid, `sub` is missing, or the token
    is not an access token at all: OAuth `state` tokens (they carry `purpose`)
    share the signing key but must never be accepted as a Bearer credential.
    """
    settings = get_settings()
    try:
        payload = pyjwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except pyjwt.PyJWTError:
        return None
    if "purpose" in payload or not payload.get("sub"):
        return None
    return payload


def decode_access_token(token: str) -> str | None:
    """Return the subject of a full-access token, or None if invalid/expired.

    Scoped tokens are deliberately rejected here: any caller of this helper
    expects a token that may do anything its user can, and a limited token
    must never be mistaken for one. Callers that handle scoped tokens use
    `decode_access_claims` and enforce the scope explicitly.
    """
    payload = decode_access_claims(token)
    if payload is None or SCOPE_CLAIM in payload:
        return None
    return payload["sub"]


_OAUTH_STATE_PURPOSE = (
    "gmail_oauth_state"  # kept as the default: existing Gmail call sites are unchanged
)


def create_oauth_state_token(
    user_id: int, expires_minutes: int = 10, purpose: str = _OAUTH_STATE_PURPOSE
) -> str:
    """Short-lived, signed `state` value for an OAuth redirect round-trip.

    Google's callback is a plain browser GET — it can't carry a Bearer token —
    so this is how the callback proves it corresponds to the admin who
    started the flow (CSRF protection + user binding), without a new secret
    or storage: it reuses JWT_SECRET, the same trust root as every other
    token in the app.

    `purpose` scopes the token to one specific OAuth domain (Gmail, Google
    Calendar, Google Contacts, ...) — each domain uses its own value (see
    `mail/router.py`, `gcalendar/router.py`, `gcontacts/router.py`) so a
    state token minted for one callback can never be replayed against a
    different one, even though all three reuse this same helper.
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": str(user_id),
        "purpose": purpose,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_oauth_state_token(
    token: str, purpose: str = _OAUTH_STATE_PURPOSE
) -> int | None:
    """Return the user id embedded in a state token, or None if invalid/expired/wrong purpose."""
    settings = get_settings()
    try:
        payload = pyjwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except pyjwt.PyJWTError:
        return None
    if payload.get("purpose") != purpose:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
