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
