from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserRead,
)
from auth.service import AuthError, AuthService
from database.session import get_db
from models.user import User
from services.rate_limit import rate_limiter
from utils.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _enforce_rate_limit(
    identifier: str, limit: int, window_seconds: int
) -> None:
    if not await rate_limiter.is_allowed(identifier, limit, window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, try again later",
        )


def get_auth_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AuthService:
    return AuthService(db)


Service = Annotated[AuthService, Depends(get_auth_service)]


def _http_error(exc: AuthError) -> HTTPException:
    if exc.conflict:
        code = status.HTTP_409_CONFLICT
    elif exc.forbidden:
        code = status.HTTP_403_FORBIDDEN
    else:
        code = status.HTTP_401_UNAUTHORIZED
    return HTTPException(status_code=code, detail=str(exc))


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, service: Service) -> User:
    try:
        return await service.register(
            payload.email, payload.full_name, payload.password
        )
    except AuthError as exc:
        raise _http_error(exc) from exc


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, service: Service) -> TokenResponse:
    try:
        access_token, refresh_token = await service.login(
            payload.email, payload.password
        )
    except AuthError as exc:
        raise _http_error(exc) from exc
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, service: Service) -> TokenResponse:
    try:
        access_token, refresh_token = await service.refresh(payload.refresh_token)
    except AuthError as exc:
        raise _http_error(exc) from exc
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, service: Service) -> None:
    await service.logout(payload.refresh_token)


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> User:
    return current_user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest, current_user: CurrentUser, service: Service
) -> None:
    try:
        await service.change_password(
            current_user, payload.current_password, payload.new_password
        )
    except AuthError as exc:
        raise _http_error(exc) from exc


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    payload: ForgotPasswordRequest, service: Service
) -> None:
    """Always 204, whether or not the email matches an account -- prevents
    using this endpoint to enumerate registered emails. Rate-limited per
    email (not IP) so throttling can't be sidestepped by rotating IPs."""
    settings = get_settings()
    await _enforce_rate_limit(
        f"password-reset-request:{payload.email}",
        settings.password_reset_request_limit,
        settings.password_reset_request_window_seconds,
    )
    await service.request_password_reset(payload.email)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordRequest, request: Request, service: Service
) -> None:
    """Rate-limited per IP (not email/token, since a token-guessing attempt
    carries no email) to slow down brute-forcing the token value itself."""
    settings = get_settings()
    await _enforce_rate_limit(
        f"password-reset-confirm:{_client_ip(request)}",
        settings.password_reset_confirm_limit,
        settings.password_reset_confirm_window_seconds,
    )
    try:
        await service.reset_password(payload.token, payload.new_password)
    except AuthError as exc:
        raise _http_error(exc) from exc
