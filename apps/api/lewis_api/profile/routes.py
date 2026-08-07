from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from lewis_api.auth.deps import get_current_user
from lewis_api.db.base import get_session
from lewis_api.db.models import User, UserProfile
from lewis_api.profile.resume import extract_resume_text
from lewis_api.schemas import NameIn, PrefsIn, ProfileOut

router = APIRouter(prefix="/api/profile", tags=["profile"])


async def _get_or_create(session: AsyncSession, user_id) -> UserProfile:
    profile = await session.get(UserProfile, user_id)
    if profile is None:
        profile = UserProfile(user_id=user_id, structured_prefs={})
        session.add(profile)
        await session.flush()
    return profile


@router.get("", response_model=ProfileOut)
async def get_profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserProfile:
    return await _get_or_create(session, user.id)


@router.post("/resume", response_model=ProfileOut)
async def upload_resume(
    file: UploadFile,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserProfile:
    data = await file.read()
    try:
        text = extract_resume_text(file.filename or "", data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    profile = await _get_or_create(session, user.id)
    profile.resume_text = text
    await session.commit()
    return profile


@router.put("/prefs", response_model=ProfileOut)
async def put_prefs(
    body: PrefsIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserProfile:
    profile = await _get_or_create(session, user.id)
    profile.raw_prefs_text = body.raw_prefs_text
    await session.commit()
    return profile


@router.put("/name", response_model=ProfileOut)
async def put_name(
    body: NameIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserProfile:
    profile = await _get_or_create(session, user.id)
    profile.name = body.name
    await session.commit()
    return profile
