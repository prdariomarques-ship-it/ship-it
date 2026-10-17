"""FastAPI dependencies for authentication."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import SCOPE_CLAIM, decode_access_claims
from auth.scopes import enforce_scoped_access, scoped_token_revoked
from database.session import get_db
from models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    claims = decode_access_claims(credentials.credentials)
    if claims is None:
        raise unauthorized

    if SCOPE_CLAIM in claims:
        # Scoped tokens are checked before touching the database: a revoked
        # token is a 401, an out-of-scope request a 403 (auth/scopes.py).
        if scoped_token_revoked(claims):
            raise unauthorized
        enforce_scoped_access(claims, request)

    try:
        user_id = int(claims["sub"])
    except (TypeError, ValueError):
        raise unauthorized from None

    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
