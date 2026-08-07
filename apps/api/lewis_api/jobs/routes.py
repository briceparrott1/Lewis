import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lewis_api.auth.deps import get_current_user
from lewis_api.db.base import get_session
from lewis_api.db.models import SavedJob, User
from lewis_api.schemas import SavedJobIn, SavedJobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[SavedJobOut])
async def list_jobs(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SavedJob]:
    rows = await session.scalars(
        select(SavedJob)
        .where(SavedJob.user_id == user.id)
        .order_by(SavedJob.saved_at.desc())
    )
    return list(rows)


@router.post("", response_model=SavedJobOut, status_code=201)
async def save_job(
    body: SavedJobIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SavedJob:
    job = SavedJob(user_id=user.id, **body.model_dump())
    session.add(job)
    await session.commit()
    return job


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    job = await session.get(SavedJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    await session.delete(job)
    await session.commit()
    return Response(status_code=204)
