"""JWT creation and validation."""
from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from utils.config import get_settings


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire, "iat": datetime.now(timezone.utc)}
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Return the token subject, or None if the token is invalid/expired."""
    settings = get_settings()
    try:
        payload = pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except pyjwt.PyJWTError:
        return None


_OAUTH_STATE_PURPOSE = "gmail_oauth_state"


def create_oauth_state_token(user_id: int, expires_minutes: int = 10) -> str:
    """Short-lived, signed `state` value for an OAuth redirect round-trip.

    Google's callback is a plain browser GET — it can't carry a Bearer token —
    so this is how the callback proves it corresponds to the admin who
    started the flow (CSRF protection + user binding), without a new secret
    or storage: it reuses JWT_SECRET, the same trust root as every other
    token in the app.
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": str(user_id),
        "purpose": _OAUTH_STATE_PURPOSE,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_oauth_state_token(token: str) -> int | None:
    """Return the user id embedded in a state token, or None if invalid/expired/wrong purpose."""
    settings = get_settings()
    try:
        payload = pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except pyjwt.PyJWTError:
        return None
    if payload.get("purpose") != _OAUTH_STATE_PURPOSE:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
