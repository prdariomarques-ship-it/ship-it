from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserRead,
)
from auth.service import AuthError, AuthService
from database.session import get_db
from models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AuthService:
    return AuthService(db)


Service = Annotated[AuthService, Depends(get_auth_service)]


def _http_error(exc: AuthError) -> HTTPException:
    code = status.HTTP_409_CONFLICT if exc.conflict else status.HTTP_401_UNAUTHORIZED
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
