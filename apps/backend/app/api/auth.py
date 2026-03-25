"""Authentication routes: register/login/me with JWT persistence."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.core.security import create_access_token, hash_password, verify_password
from app.database.models import User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=128)
    email: EmailStr
    password: str = Field(min_length=6, max_length=256)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    username: str
    email: str
    role: UserRole
    is_active: bool


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    existing_q = await session.execute(
        select(User).where((User.username == req.username) | (User.email == req.email))
    )
    existing = existing_q.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or email already exists")

    user = User(
        username=req.username,
        email=str(req.email),
        hashed_password=hash_password(req.password),
        role=UserRole.viewer,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return {"id": user.id, "username": user.username, "email": user.email, "role": user.role}


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_db_session)) -> TokenResponse:
    q = await session.execute(select(User).where(User.username == req.username))
    user = q.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(subject=user.username, role=user.role.value)
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
    )

