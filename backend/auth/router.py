from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from auth.jwt import create_access_token
from auth.password import hash_password, verify_password
from auth.schemas import LoginRequest, TokenResponse, UserCreate, UserRead
from database.session import get_db
from models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: DbSession) -> User:
    existing = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> User:
    return current_user
