from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lewis_api.auth.deps import get_current_user
from lewis_api.auth.security import (
    COOKIE_NAME,
    create_access_token,
    hash_password,
    verify_password,
)
from lewis_api.config import get_settings
from lewis_api.db.base import get_session
from lewis_api.db.models import User
from lewis_api.schemas import LoginIn, SignupIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(response: Response, user_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_access_token(user_id),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_expire_days * 86400,
        path="/",
    )


@router.post("/signup", response_model=UserOut, status_code=201)
async def signup(
    body: SignupIn, response: Response, session: AsyncSession = Depends(get_session)
) -> User:
    existing = await session.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email, password_hash=hash_password(body.password))
    session.add(user)
    await session.flush()
    _set_cookie(response, str(user.id))
    await session.commit()
    return user


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginIn, response: Response, session: AsyncSession = Depends(get_session)
) -> User:
    user = await session.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _set_cookie(response, str(user.id))
    return user


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
