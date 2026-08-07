import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lewis_api.agent.graph import run_agent
from lewis_api.auth.deps import get_current_user
from lewis_api.db.base import async_session_maker, get_session
from lewis_api.db.models import ServedJob, User, UserProfile
from lewis_api.schemas import ChatIn

router = APIRouter(prefix="/api", tags=["chat"])

logger = logging.getLogger(__name__)


def _frame(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"


@router.post("/chat")
async def chat(
    body: ChatIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    profile = await session.get(UserProfile, user.id)
    resume_text = (profile.resume_text if profile else "") or ""
    prior_prefs = (profile.structured_prefs if profile else {}) or {}  # noqa: F841
    user_name = (profile.name if profile else None) or None
    served_rows = await session.scalars(
        select(ServedJob.job_key).where(ServedJob.user_id == user.id)
    )
    served_keys = list(served_rows)
    graph = request.app.state.agent_graph
    thread_id = f"{user.id}:{body.conversation_id}"
    user_id = user.id

    async def gen():
        newly_served: list[str] = []
        async for event in run_agent(
            graph,
            user_id=str(user_id),
            resume_text=resume_text,
            served_keys=served_keys,
            message=body.message,
            thread_id=thread_id,
            user_name=user_name,
        ):
            if event["type"] == "done":
                newly_served = event.get("served_keys", [])
            yield _frame(event)

        # Use a fresh, request-independent session: the request-scoped `session`
        # may already be torn down by the time the stream finishes. Dedupe keys
        # (they were just excluded from the search, so collisions are unlikely)
        # and guard the commit so a duplicate/constraint error can't crash the
        # stream after results have already been sent to the client.
        deduped = list(dict.fromkeys(newly_served))
        if deduped:
            async with async_session_maker() as write_session:
                for key in deduped:
                    write_session.add(ServedJob(user_id=user_id, job_key=key))
                try:
                    await write_session.commit()
                except Exception:
                    logger.exception(
                        "Failed to record served jobs for user %s", user_id
                    )
                    await write_session.rollback()

    return StreamingResponse(gen(), media_type="text/event-stream")
