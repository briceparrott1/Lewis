# Foundation & Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Lewis monorepo and a working, authenticated FastAPI backend — DB, JWT-cookie auth, resume-profile handling, and saved/served job storage — verifiable by tests and curl, with the agent/chat layer deliberately left for Plan 2.

**Architecture:** Single FastAPI service (async SQLAlchemy 2.0 → Postgres, Alembic migrations) that will later also serve the SPA and the agent. This plan builds everything the agent and frontend will sit on: config, DB session lifecycle, models, auth (JWT in an httpOnly cookie), the resume/prefs profile endpoints, and jobs CRUD. Postgres runs via docker-compose for local dev and tests.

**Tech Stack:** Python 3.12, `uv`, FastAPI, SQLAlchemy 2.0 (async, `asyncpg`), Alembic, `pydantic-settings`, PyJWT, `argon2-cffi`, `python-multipart`, `pypdf`, `python-docx`; tests with `pytest`, `pytest-asyncio`, `httpx`.

## Global Constraints

- Python **3.12**; dependency management with **`uv`**.
- **PEP 8** compliant; formatted with **Black (88 cols)**; imports sorted by **Ruff**.
- `ruff check .` and `black --check .` must pass.
- **Type hints on all public functions.** No unused imports. No overly complex functions.
- **TDD:** every behavior change ships with a minimal test. Tests must pass before commit.
- All API routes are under the **`/api`** prefix.
- Every data access is scoped to the authenticated **`user_id`**.
- Secrets come only from env (`.env` locally, gitignored). Never hard-code secrets.
- Reference design: `docs/superpowers/specs/2026-08-06-lewis-architecture-design.md`; requirements: `docs/prd/backend-prd.md`.

---

## File Structure

```
lewis/
├─ pnpm-workspace.yaml            # declares apps/*, packages/* (frontend added in Plan 3)
├─ docker-compose.yml             # postgres (+ api service)
├─ .env.example                   # committed template (no secrets)
└─ apps/
   └─ api/
      ├─ pyproject.toml           # deps + tool config (ruff/black/pytest)
      ├─ Dockerfile               # api image (used by compose + Railway later)
      ├─ alembic.ini
      ├─ alembic/
      │  ├─ env.py                # async migration env, points at Base.metadata
      │  └─ versions/             # migration files
      ├─ lewis_api/
      │  ├─ __init__.py
      │  ├─ main.py               # FastAPI app, lifespan, router mounting
      │  ├─ config.py             # Settings (pydantic-settings) + get_settings()
      │  ├─ schemas.py            # Pydantic request/response models
      │  ├─ db/
      │  │  ├─ __init__.py
      │  │  ├─ base.py            # Base, engine, async_session_maker, get_session()
      │  │  └─ models.py          # User, UserProfile, SavedJob, ServedJob
      │  ├─ auth/
      │  │  ├─ __init__.py
      │  │  ├─ security.py        # hash/verify password, create/decode JWT
      │  │  ├─ deps.py            # get_current_user()
      │  │  └─ routes.py          # /api/auth/*
      │  ├─ profile/
      │  │  ├─ __init__.py
      │  │  ├─ resume.py          # extract_resume_text()
      │  │  └─ routes.py          # /api/profile/*
      │  └─ jobs/
      │     ├─ __init__.py
      │     └─ routes.py          # /api/jobs/*
      └─ tests/
         ├─ conftest.py           # app/client/session fixtures (test Postgres)
         ├─ test_health.py
         ├─ test_security.py
         ├─ test_auth.py
         ├─ test_profile.py
         └─ test_jobs.py
```

**Responsibilities:** `config.py` owns all env-derived settings. `db/base.py` owns engine/session/DI. `db/models.py` owns the ORM tables only. `auth/security.py` is pure crypto/JWT (no DB). `auth/deps.py` bridges cookie→user. Each feature package (`auth`, `profile`, `jobs`) owns its router. `schemas.py` holds shared Pydantic I/O models.

All commands below run from `apps/api/` unless stated. Prefix Python commands with `uv run`.

---

### Task 1: Monorepo scaffold, FastAPI skeleton, docker-compose, health check

**Files:**
- Create: `pnpm-workspace.yaml`, `docker-compose.yml`, `.env.example`
- Create: `apps/api/pyproject.toml`, `apps/api/Dockerfile`
- Create: `apps/api/lewis_api/__init__.py`, `apps/api/lewis_api/config.py`, `apps/api/lewis_api/main.py`
- Test: `apps/api/tests/test_health.py`, `apps/api/tests/conftest.py`

**Interfaces:**
- Produces: `lewis_api.config.Settings` (fields: `database_url: str`, `jwt_secret: str`, `jwt_expire_days: int = 7`, `max_results: int = 6`, `cookie_secure: bool = False`, `anthropic_api_key: str = ""`), `get_settings() -> Settings` (cached). `lewis_api.main.app` (FastAPI instance). `GET /api/health` → `{"status": "ok"}`.

- [ ] **Step 1: Create the workspace + compose + env template**

`pnpm-workspace.yaml`:
```yaml
packages:
  - "apps/*"
  - "packages/*"
```

`docker-compose.yml`:
```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-lewis}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-lewis_local_dev}
      POSTGRES_DB: ${POSTGRES_DB:-lewis}
    ports:
      - "5432:5432"
    volumes:
      - lewis_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-lewis}"]
      interval: 5s
      timeout: 5s
      retries: 5
volumes:
  lewis_pgdata:
```

`.env.example` (committed — mirrors `.env` but with NO secret values):
```dotenv
ANTHROPIC_API_KEY=
JWT_SECRET=change-me-in-prod
POSTGRES_USER=lewis
POSTGRES_PASSWORD=lewis_local_dev
POSTGRES_DB=lewis
DATABASE_URL=postgresql+asyncpg://lewis:lewis_local_dev@db:5432/lewis
TEST_DATABASE_URL=postgresql+asyncpg://lewis:lewis_local_dev@localhost:5432/lewis
JWT_EXPIRE_DAYS=7
MAX_RESULTS=6
COOKIE_SECURE=false
AGENT_MODEL=claude-haiku-4-5-20251001
```

Create the separate test database once (used by the pytest suite, kept distinct
from the dev/migration DB so `create_all`/`drop_all` never corrupts migrations):
```bash
docker compose up -d db
docker compose exec -T db psql -U lewis -d postgres -c "CREATE DATABASE lewis_test;"
```

- [ ] **Step 2: Create `apps/api/pyproject.toml`**

```toml
[project]
name = "lewis-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "pydantic-settings>=2.4",
    "pyjwt>=2.9",
    "argon2-cffi>=23.1",
    "python-multipart>=0.0.9",
    "pypdf>=5.0",
    "python-docx>=1.1",
]

[dependency-groups]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "httpx>=0.27", "ruff>=0.6", "black>=24.8"]

[tool.black]
line-length = 88

[tool.ruff]
line-length = 88

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.setuptools.packages.find]
include = ["lewis_api*"]
```

- [ ] **Step 3: Create `lewis_api/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://lewis:lewis_local_dev@localhost:5432/lewis"
    jwt_secret: str = "change-me-in-prod"
    jwt_expire_days: int = 7
    max_results: int = 6
    cookie_secure: bool = False
    anthropic_api_key: str = ""
    agent_model: str = "claude-haiku-4-5-20251001"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Create `lewis_api/__init__.py` (empty) and `lewis_api/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="Lewis API")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Create `apps/api/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml ./
RUN uv sync --no-dev
COPY . .
CMD ["uv", "run", "uvicorn", "lewis_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 6: Write the failing test** — `apps/api/tests/conftest.py`

```python
import httpx
import pytest
from httpx import ASGITransport

from lewis_api.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

`apps/api/tests/test_health.py`:
```python
async def test_health_ok(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 7: Install deps and run the test**

Run:
```bash
cd apps/api && uv sync && uv run pytest tests/test_health.py -v
```
Expected: PASS (1 test).

- [ ] **Step 8: Verify lint/format**

Run: `uv run ruff check . && uv run black --check .`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: scaffold monorepo, FastAPI skeleton, compose, health endpoint"
```

---

### Task 2: Async DB layer (engine, session, Base) + Alembic

**Files:**
- Create: `apps/api/lewis_api/db/__init__.py`, `apps/api/lewis_api/db/base.py`
- Create: `apps/api/alembic.ini`, `apps/api/alembic/env.py`
- Modify: `apps/api/tests/conftest.py` (add DB session + override fixtures)

**Interfaces:**
- Produces: `db.base.Base` (DeclarativeBase), `db.base.engine`, `db.base.async_session_maker`, `db.base.get_session() -> AsyncIterator[AsyncSession]` (FastAPI dependency).

- [ ] **Step 1: Create `lewis_api/db/__init__.py` (empty) and `lewis_api/db/base.py`**

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from lewis_api.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, future=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session
```

- [ ] **Step 2: Initialize Alembic (async template)**

Run: `uv run alembic init -t async alembic`

- [ ] **Step 3: Point Alembic at our metadata** — edit `alembic/env.py`

Replace the `target_metadata = None` line and DB URL wiring with:
```python
from lewis_api.config import get_settings
from lewis_api.db.base import Base
from lewis_api.db import models  # noqa: F401  (ensures models are imported)

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", get_settings().database_url)
```
(Leave the rest of the async template's `run_migrations_online` intact.)

Note: `lewis_api/db/models.py` does not exist until Task 3 — create an empty `models.py` now so the import resolves:
```bash
touch lewis_api/db/models.py
```

- [ ] **Step 4: Add DB fixtures to `tests/conftest.py`**

Replace the file with:
```python
import os

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from lewis_api.db import models  # noqa: F401  (registers all tables on Base)
from lewis_api.db.base import Base, get_session
from lewis_api.main import app

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    # Separate DB from the dev/migration DB so create_all/drop_all can't
    # corrupt migration state in `lewis`.
    "postgresql+asyncpg://lewis:lewis_local_dev@localhost:5432/lewis_test",
)


@pytest.fixture
async def db_session():
    """Fresh schema per test. NullPool keeps every connection on the test's own
    event loop, avoiding pytest-asyncio 'different event loop' errors with asyncpg.
    Cheap for our handful of small tables."""
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    session = maker()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def client(db_session):
    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

(If pytest prints an "asyncio_default_fixture_loop_scope is unset" warning, add
`asyncio_default_fixture_loop_scope = "function"` under `[tool.pytest.ini_options]`
in `pyproject.toml` — it silences the warning; tests pass either way.)

- [ ] **Step 5: Start Postgres and confirm health test still passes with DB wiring**

Run (from repo root): `docker compose up -d db`
Then: `cd apps/api && uv run pytest tests/test_health.py -v`
Expected: PASS. (Confirms the engine imports and app still boots.)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: async SQLAlchemy engine/session, Base, Alembic async env, test DB fixtures"
```

---

### Task 3: User model + migration

**Files:**
- Modify: `apps/api/lewis_api/db/models.py`
- Create: `apps/api/alembic/versions/<hash>_users.py` (generated)
- Test: `apps/api/tests/test_auth.py` (start with a model persistence test)

**Interfaces:**
- Produces: `db.models.User` with columns `id: UUID` (pk, default uuid4), `email: str` (unique, not null), `password_hash: str` (not null), `created_at: datetime` (server default now).

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_auth.py`

```python
import uuid

from lewis_api.db.models import User


async def test_user_persists(db_session):
    user = User(email="a@b.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    assert isinstance(user.id, uuid.UUID)
    assert user.created_at is not None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_auth.py::test_user_persists -v`
Expected: FAIL (`ImportError: cannot import name 'User'`).

- [ ] **Step 3: Implement `lewis_api/db/models.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from lewis_api.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_auth.py::test_user_persists -v`
Expected: PASS.

- [ ] **Step 5: Generate and apply the migration**

Run:
```bash
uv run alembic revision --autogenerate -m "users"
uv run alembic upgrade head
```
Expected: a version file appears under `alembic/versions/`; `upgrade` succeeds against the compose DB.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: User model + initial migration"
```

---

### Task 4: Password hashing + JWT (pure, no DB)

**Files:**
- Create: `apps/api/lewis_api/auth/__init__.py`, `apps/api/lewis_api/auth/security.py`
- Test: `apps/api/tests/test_security.py`

**Interfaces:**
- Produces: `auth.security.hash_password(password: str) -> str`, `verify_password(password: str, password_hash: str) -> bool`, `create_access_token(user_id: str) -> str`, `decode_access_token(token: str) -> str | None` (returns the `sub` user_id, or `None` if invalid/expired).

- [ ] **Step 1: Write the failing tests** — `apps/api/tests/test_security.py`

```python
from lewis_api.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_roundtrip():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_jwt_roundtrip():
    token = create_access_token("user-123")
    assert decode_access_token(token) == "user-123"


def test_jwt_rejects_garbage():
    assert decode_access_token("not.a.jwt") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_security.py -v`
Expected: FAIL (`ModuleNotFoundError: lewis_api.auth.security`).

- [ ] **Step 3: Implement** — `lewis_api/auth/__init__.py` (empty) and `lewis_api/auth/security.py`

```python
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from lewis_api.config import get_settings

_ph = PasswordHasher()
_ALGO = "HS256"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token, get_settings().jwt_secret, algorithms=[_ALGO]
        )
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_security.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: argon2 password hashing + JWT create/decode"
```

---

### Task 5: Auth routes (signup, login, logout, me) with httpOnly cookie

**Files:**
- Create: `apps/api/lewis_api/schemas.py`
- Create: `apps/api/lewis_api/auth/routes.py`
- Modify: `apps/api/lewis_api/main.py` (include the auth router)
- Test: `apps/api/tests/test_auth.py` (add route tests)

**Interfaces:**
- Consumes: `auth.security.*`, `db.models.User`, `db.base.get_session`.
- Produces: `schemas.SignupIn`, `schemas.LoginIn`, `schemas.UserOut`; router at `/api/auth` with `POST /signup`, `POST /login`, `POST /logout`, `GET /me`. Cookie name is `access_token`.

- [ ] **Step 1: Create `lewis_api/schemas.py`**

```python
import uuid

from pydantic import BaseModel, EmailStr


class SignupIn(BaseModel):
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str

    model_config = {"from_attributes": True}
```
(Note: `EmailStr` requires `email-validator`; add `"email-validator>=2.0"` to `dependencies` in `pyproject.toml` and re-run `uv sync`.)

- [ ] **Step 2: Write the failing route tests** — append to `apps/api/tests/test_auth.py`

```python
COOKIE = "access_token"


async def test_signup_sets_cookie(client):
    resp = await client.post(
        "/api/auth/signup", json={"email": "x@y.com", "password": "hunter2"}
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "x@y.com"
    assert COOKIE in resp.cookies


async def test_login_and_me(client):
    await client.post(
        "/api/auth/signup", json={"email": "m@e.com", "password": "hunter2"}
    )
    login = await client.post(
        "/api/auth/login", json={"email": "m@e.com", "password": "hunter2"}
    )
    assert login.status_code == 200
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "m@e.com"


async def test_login_wrong_password(client):
    await client.post(
        "/api/auth/signup", json={"email": "w@e.com", "password": "hunter2"}
    )
    bad = await client.post(
        "/api/auth/login", json={"email": "w@e.com", "password": "nope"}
    )
    assert bad.status_code == 401


async def test_me_requires_auth(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_auth.py -v`
Expected: route tests FAIL (404 / import errors).

- [ ] **Step 4: Implement `lewis_api/auth/routes.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lewis_api.auth.deps import get_current_user
from lewis_api.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from lewis_api.config import get_settings
from lewis_api.db.base import get_session
from lewis_api.db.models import User
from lewis_api.schemas import LoginIn, SignupIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE_NAME = "access_token"


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
```

- [ ] **Step 5: Create the auth dependency stub it needs** — `lewis_api/auth/deps.py`

(Full version is Task 6; create the working version now since routes import it.)
```python
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from lewis_api.auth.routes import COOKIE_NAME  # noqa: E402
```
Wait — that would be a circular import. Instead define `COOKIE_NAME` in `deps.py` is wrong too. **Resolution:** move `COOKIE_NAME` to `security.py`. Edit `security.py` to add `COOKIE_NAME = "access_token"` at top, and in `routes.py` replace the local definition with `from lewis_api.auth.security import COOKIE_NAME`. Then write `deps.py`:

```python
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lewis_api.auth.security import COOKIE_NAME, decode_access_token
from lewis_api.db.base import get_session
from lewis_api.db.models import User


async def get_current_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    token = request.cookies.get(COOKIE_NAME)
    user_id = decode_access_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
```

- [ ] **Step 6: Include the router** — edit `lewis_api/main.py`

```python
from fastapi import FastAPI

from lewis_api.auth.routes import router as auth_router

app = FastAPI(title="Lewis API")
app.include_router(auth_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 7: Run all auth tests**

Run: `uv run pytest tests/test_auth.py -v`
Expected: PASS (all).

- [ ] **Step 8: Lint/format then commit**

```bash
uv run ruff check . && uv run black --check .
git add -A
git commit -m "feat: auth routes (signup/login/logout/me) with httpOnly JWT cookie"
```

---

### Task 6: `get_current_user` hardening + protected-route coverage

**Files:**
- Modify: `apps/api/tests/test_auth.py` (add expired/invalid-token tests)

**Interfaces:**
- Consumes: `auth.deps.get_current_user` (defined in Task 5).

- [ ] **Step 1: Write failing tests** — append to `apps/api/tests/test_auth.py`

```python
async def test_me_rejects_tampered_cookie(client):
    client.cookies.set("access_token", "tampered.token.value")
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run**

Run: `uv run pytest tests/test_auth.py::test_me_rejects_tampered_cookie -v`
Expected: PASS (the Task 5 `deps.py` already handles this — this test locks the behavior in).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: cover tampered-cookie rejection for get_current_user"
```

---

### Task 7: UserProfile model, resume extraction, profile routes

**Files:**
- Modify: `apps/api/lewis_api/db/models.py` (add `UserProfile`)
- Create: `apps/api/lewis_api/profile/__init__.py`, `apps/api/lewis_api/profile/resume.py`, `apps/api/lewis_api/profile/routes.py`
- Modify: `apps/api/lewis_api/schemas.py` (add profile schemas), `apps/api/lewis_api/main.py` (include router)
- Create: migration
- Test: `apps/api/tests/test_profile.py`

**Interfaces:**
- Produces: `db.models.UserProfile` (`user_id: UUID` pk/fk, `resume_text: str | None`, `raw_prefs_text: str | None`, `structured_prefs: dict` jsonb default `{}`). `profile.resume.extract_resume_text(filename: str, data: bytes) -> str`. `schemas.ProfileOut`, `schemas.PrefsIn`. Router `/api/profile`: `GET ""`, `POST /resume`, `PUT /prefs`.

- [ ] **Step 1: Write failing tests** — `apps/api/tests/test_profile.py`

```python
import io

from docx import Document

from lewis_api.profile.resume import extract_resume_text


def _docx_bytes(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extract_docx():
    data = _docx_bytes("Forward Deployed Engineer, Python, SQL")
    text = extract_resume_text("resume.docx", data)
    assert "Forward Deployed Engineer" in text


async def _signup(client, email="p@e.com"):
    await client.post("/api/auth/signup", json={"email": email, "password": "hunter2"})


async def test_upload_resume_and_get_profile(client):
    await _signup(client)
    data = _docx_bytes("Python engineer")
    resp = await client.post(
        "/api/profile/resume",
        files={"file": ("r.docx", data,
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 200
    assert "Python engineer" in resp.json()["resume_text"]

    prof = await client.get("/api/profile")
    assert "Python engineer" in prof.json()["resume_text"]


async def test_put_prefs(client):
    await _signup(client, "pref@e.com")
    resp = await client.put("/api/profile/prefs", json={"raw_prefs_text": "FDE in SF"})
    assert resp.status_code == 200
    prof = await client.get("/api/profile")
    assert prof.json()["raw_prefs_text"] == "FDE in SF"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_profile.py -v`
Expected: FAIL (imports/routes missing).

- [ ] **Step 3: Add `UserProfile` to `lewis_api/db/models.py`**

```python
from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_prefs_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_prefs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
```
(Add the new imports alongside existing ones; keep imports Ruff-sorted.)

- [ ] **Step 4: Implement `lewis_api/profile/resume.py`**

```python
import io


def extract_resume_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if name.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs).strip()
    raise ValueError("Unsupported file type; use PDF or DOCX")
```

- [ ] **Step 5: Add schemas** — append to `lewis_api/schemas.py`

```python
class ProfileOut(BaseModel):
    resume_text: str | None
    raw_prefs_text: str | None
    structured_prefs: dict

    model_config = {"from_attributes": True}


class PrefsIn(BaseModel):
    raw_prefs_text: str
```

- [ ] **Step 6: Implement `lewis_api/profile/routes.py`** (and empty `__init__.py`)

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from lewis_api.auth.deps import get_current_user
from lewis_api.db.base import get_session
from lewis_api.db.models import User, UserProfile
from lewis_api.profile.resume import extract_resume_text
from lewis_api.schemas import PrefsIn, ProfileOut

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
```

- [ ] **Step 7: Include router** — add to `lewis_api/main.py`

```python
from lewis_api.profile.routes import router as profile_router
app.include_router(profile_router)
```

- [ ] **Step 8: Run tests, migrate, lint, commit**

```bash
uv run pytest tests/test_profile.py -v          # expect PASS
uv run alembic revision --autogenerate -m "user_profiles"
uv run alembic upgrade head
uv run ruff check . && uv run black --check .
git add -A
git commit -m "feat: user profile — resume extraction + profile/prefs routes + migration"
```

---

### Task 8: SavedJob + ServedJob models and jobs routes

**Files:**
- Modify: `apps/api/lewis_api/db/models.py` (add `SavedJob`, `ServedJob`)
- Modify: `apps/api/lewis_api/schemas.py` (add job schemas)
- Create: `apps/api/lewis_api/jobs/__init__.py`, `apps/api/lewis_api/jobs/routes.py`
- Modify: `apps/api/lewis_api/main.py` (include router)
- Create: migration
- Test: `apps/api/tests/test_jobs.py`

**Interfaces:**
- Produces: `db.models.SavedJob` (`id: UUID` pk, `user_id` fk, `source`, `company`, `title`, `location`, `url`, `score: int | None`, `reason: str | None`, `raw: dict` jsonb, `saved_at`). `db.models.ServedJob` (`user_id` fk, `job_key: str`, `source_id: str | None`, `served_at`; pk `(user_id, job_key)`). `schemas.SavedJobIn`, `schemas.SavedJobOut`. Router `/api/jobs`: `GET ""`, `POST ""`, `DELETE /{job_id}`.
- Note for Plan 2: the agent will write `ServedJob` rows and read them; this task only creates the table + jobs CRUD, not the agent wiring.

- [ ] **Step 1: Write failing tests** — `apps/api/tests/test_jobs.py`

```python
async def _signup(client, email="j@e.com"):
    await client.post("/api/auth/signup", json={"email": email, "password": "hunter2"})


def _job_payload():
    return {
        "source": "ashby",
        "company": "Ramp",
        "title": "Forward Deployed Engineer",
        "location": "New York",
        "url": "https://jobs.ashbyhq.com/ramp/abc",
        "score": 92,
        "reason": "Strong FDE match",
    }


async def test_save_list_delete(client):
    await _signup(client)
    save = await client.post("/api/jobs", json=_job_payload())
    assert save.status_code == 201
    job_id = save.json()["id"]

    listing = await client.get("/api/jobs")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    delete = await client.delete(f"/api/jobs/{job_id}")
    assert delete.status_code == 204

    listing2 = await client.get("/api/jobs")
    assert listing2.json() == []


async def test_jobs_require_auth(client):
    resp = await client.get("/api/jobs")
    assert resp.status_code == 401


async def test_jobs_are_user_scoped(client):
    await _signup(client, "owner@e.com")
    await client.post("/api/jobs", json=_job_payload())
    await client.post("/api/auth/logout")
    await _signup(client, "other@e.com")
    listing = await client.get("/api/jobs")
    assert listing.json() == []
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_jobs.py -v`
Expected: FAIL.

- [ ] **Step 3: Add models to `lewis_api/db/models.py`**

```python
from datetime import datetime as _dt

from sqlalchemy import DateTime, Integer


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    company: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    saved_at: Mapped[_dt] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServedJob(Base):
    __tablename__ = "served_jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True, index=True
    )
    job_key: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    served_at: Mapped[_dt] = mapped_column(DateTime(timezone=True), server_default=func.now())
```
(Merge imports with existing ones; keep them Ruff-sorted and de-duplicated.)

- [ ] **Step 4: Add schemas** — append to `lewis_api/schemas.py`

```python
from datetime import datetime


class SavedJobIn(BaseModel):
    source: str
    company: str
    title: str
    location: str | None = None
    url: str
    score: int | None = None
    reason: str | None = None
    raw: dict = {}


class SavedJobOut(BaseModel):
    id: uuid.UUID
    source: str
    company: str
    title: str
    location: str | None
    url: str
    score: int | None
    reason: str | None
    saved_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Implement `lewis_api/jobs/routes.py`** (and empty `__init__.py`)

```python
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
        select(SavedJob).where(SavedJob.user_id == user.id).order_by(SavedJob.saved_at.desc())
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
```

- [ ] **Step 6: Include router** — add to `lewis_api/main.py`

```python
from lewis_api.jobs.routes import router as jobs_router
app.include_router(jobs_router)
```

- [ ] **Step 7: Run tests, migrate, lint, commit**

```bash
uv run pytest -v                                 # full suite, expect all PASS
uv run alembic revision --autogenerate -m "saved_and_served_jobs"
uv run alembic upgrade head
uv run ruff check . && uv run black --check .
git add -A
git commit -m "feat: SavedJob/ServedJob models + jobs CRUD routes + migration"
```

---

### Task 9: End-to-end smoke via curl + README

**Files:**
- Create: `README.md` (run instructions)

- [ ] **Step 1: Bring up the stack and run the API**

```bash
docker compose up -d db
cd apps/api && uv run alembic upgrade head
uv run uvicorn lewis_api.main:app --reload --port 8000
```

- [ ] **Step 2: Manual smoke (new terminal)**

```bash
curl -i -c cookies.txt -X POST localhost:8000/api/auth/signup \
  -H 'content-type: application/json' -d '{"email":"a@b.com","password":"hunter2"}'
curl -s -b cookies.txt localhost:8000/api/auth/me
curl -s -b cookies.txt -X PUT localhost:8000/api/profile/prefs \
  -H 'content-type: application/json' -d '{"raw_prefs_text":"FDE in SF"}'
curl -s -b cookies.txt localhost:8000/api/profile
```
Expected: signup returns 201 + `Set-Cookie`; `/me` returns the user; prefs round-trip.

- [ ] **Step 3: Write `README.md`** documenting the above (prereqs: Docker, `uv`; how to run tests: `cd apps/api && uv run pytest`).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs: backend run instructions + e2e smoke"
```

---

## Self-Review

**Spec coverage (backend PRD B1–B11):** B1–B3 auth → Tasks 4–6. B4–B5 profile/resume → Task 7. B6 `/chat` SSE → **Plan 2** (explicitly out of scope here; noted). B7 jobs CRUD → Task 8. B8 disconnect + B10 checkpointer `setup()` → **Plan 2** (agent/chat). B9 SPA serving → **Plan 3** (added when `dist` exists). B10 Alembic app tables → Tasks 3/7/8. B11 config → Task 1. Data model (spec §6): users/profiles/saved/served all created. Gaps are intentional and assigned to later plans.

**Placeholder scan:** No TBD/TODO; every code and test step contains real content. The one inline "wait — circular import" note in Task 5 Step 5 is a deliberate, resolved instruction (move `COOKIE_NAME` to `security.py`), not a placeholder.

**Type consistency:** `get_session`, `get_current_user`, `User`, `UserProfile`, `SavedJob`, `ServedJob`, `create_access_token`/`decode_access_token`, `extract_resume_text`, and the `schemas.*` models are referenced with identical names/signatures across tasks. Cookie name is centralized as `security.COOKIE_NAME`.

## Notes carried to Plan 2 (Agent Core & Chat)

- `ServedJob` table exists; agent's `exclude_served`/`record_served` will use it.
- `structured_prefs` jsonb on `UserProfile` is where the agent persists learned prefs.
- Checkpointer `AsyncPostgresSaver.setup()` + `POST /api/chat` SSE are Plan 2.
- `anthropic_api_key` already in `Settings`.
