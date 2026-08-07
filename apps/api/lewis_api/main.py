from fastapi import FastAPI

from lewis_api.auth.routes import router as auth_router

app = FastAPI(title="Lewis API")
app.include_router(auth_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
