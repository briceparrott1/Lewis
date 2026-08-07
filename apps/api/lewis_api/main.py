from fastapi import FastAPI

from lewis_api.auth.routes import router as auth_router
from lewis_api.profile.routes import router as profile_router

app = FastAPI(title="Lewis API")
app.include_router(auth_router)
app.include_router(profile_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
