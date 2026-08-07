from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from langgraph.checkpoint.memory import MemorySaver

from lewis_api.agent.graph import build_graph
from lewis_api.agent.llm import AnthropicLLM
from lewis_api.agent.sources.boards import fetch_all_boards
from lewis_api.agent.sources.seed import load_seed
from lewis_api.auth.routes import router as auth_router
from lewis_api.chat.routes import router as chat_router
from lewis_api.jobs.routes import router as jobs_router
from lewis_api.profile.routes import router as profile_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    seed = load_seed()

    async def fetch_boards(entries, _client):
        async with httpx.AsyncClient(timeout=8) as client:
            return await fetch_all_boards(entries, client)

    # MemorySaver keeps this minimal for v1; swap for AsyncPostgresSaver to
    # persist clarify state across restarts (see docs/superpowers plan notes).
    app.state.agent_graph = build_graph(
        AnthropicLLM(), fetch_boards, seed, MemorySaver()
    )
    yield


app = FastAPI(title="Lewis API", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(jobs_router)
app.include_router(chat_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        return FileResponse(_DIST / "index.html")
