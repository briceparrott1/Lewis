# Lewis

An agent that automates finding job roles for you. You give it your **resume** and a
few sentences about the roles you want (e.g. *"new grad, high-growth FDE roles in San
Francisco"*); it scans Greenhouse + Ashby job boards, ranks matches against your
resume and priorities, and surfaces the best few — never repeating a job it has
already shown you.

- **Design:** [`docs/superpowers/specs/2026-08-06-lewis-architecture-design.md`](docs/superpowers/specs/2026-08-06-lewis-architecture-design.md)
- **PRDs:** [`docs/prd/`](docs/prd/)
- **Plans:** [`docs/superpowers/plans/`](docs/superpowers/plans/)

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI + LangGraph (Python 3.12) |
| DB | Postgres + SQLAlchemy 2.0 (async) + Alembic |
| Auth | JWT in an httpOnly cookie (argon2id hashing) |
| Frontend | React + Vite + TypeScript + Tailwind *(Plan 3)* |
| Agent LLM | Claude, default `claude-haiku-4-5` (env `AGENT_MODEL`) |
| Local dev | Docker Compose (Postgres) |

This repo is a monorepo. The backend lives in [`apps/api`](apps/api); the frontend
(added in Plan 3) will live in `apps/web`.

## Prerequisites

- [Docker](https://www.docker.com/) (for local Postgres)
- [`uv`](https://docs.astral.sh/uv/) (Python dependency manager)

## Setup & run (backend)

```bash
# 1. Copy env template and add your Anthropic key
cp .env.example .env          # then set ANTHROPIC_API_KEY (needed by the agent, Plan 2)

# 2. Start Postgres
docker compose up -d db

# 3. Create the separate test database (once)
docker compose exec -T db psql -U lewis -d postgres -c "CREATE DATABASE lewis_test;"

# 4. Apply migrations
cd apps/api
uv sync
uv run alembic upgrade head

# 5. Run the API (serves /api/* ; the SPA is added in Plan 3)
uv run uvicorn lewis_api.main:app --reload --port 8000
```

Health check: <http://localhost:8000/api/health>

## Tests

```bash
cd apps/api
uv run pytest -q          # uses the lewis_test database
uv run ruff check .       # lint
uv run black --check .    # format
```

## API (implemented so far — Plans 1 & 2)

| Method + path | Purpose |
|---|---|
| `POST /api/auth/signup` · `login` · `logout` · `GET /api/auth/me` | Cookie-based JWT auth |
| `GET /api/profile` · `POST /api/profile/resume` · `PUT /api/profile/prefs` | Resume (PDF/DOCX) + preferences |
| `GET /api/jobs` · `POST /api/jobs` · `DELETE /api/jobs/{id}` | Saved jobs |
| `POST /api/chat` | **Streaming agent search (SSE)** |

### Quick smoke test

```bash
curl -i -c cookies.txt -X POST localhost:8000/api/auth/signup \
  -H 'content-type: application/json' -d '{"email":"you@example.com","password":"hunter2"}'
curl -s -b cookies.txt localhost:8000/api/auth/me
```

### Chat (agent search)

Requires `ANTHROPIC_API_KEY` set in `.env`. `POST /api/chat` streams Server-Sent
Events (`status`, `clarify`, `result`, `done`). It scans the seed companies'
Greenhouse/Ashby boards, filters + ranks against your resume and stated
preferences (Claude, default Haiku), returns the top few, and never repeats a job
it has already shown you.

```bash
curl -N -s -b cookies.txt -X POST localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"message":"forward deployed engineer roles, remote OK","conversation_id":"c1"}'
```

Send follow-up messages with the same `conversation_id` to continue a conversation
(e.g. to answer a clarifying question); use a new id to start fresh.

## Frontend (web app)

React + Vite + TypeScript + Tailwind SPA in [`apps/web`](apps/web): signup/login, a
one-time resume-upload onboarding gate, a streaming chat that consumes `/api/chat`,
and a saved-jobs view. Requires `pnpm` (`corepack enable pnpm`).

```bash
cd apps/web
pnpm install
pnpm dev        # http://localhost:5173, proxies /api → http://localhost:8000
pnpm test       # Vitest
pnpm build      # outputs dist/ (served by FastAPI in prod)
```

In production the built `apps/web/dist` is served by FastAPI (single origin), so the
whole app runs from one service. The root `Dockerfile` builds the web app and copies
it into the API image.

## Project status

- ✅ **Plan 1 — Foundation & Backend** (auth, profile, jobs, DB, migrations)
- ✅ **Plan 2 — Agent core & chat** (LangGraph agent + `/api/chat` SSE)
- ✅ **Plan 3 — Frontend** (React SPA: signup, onboarding, streaming chat, saved jobs)

**Lewis is a complete, runnable product:** `docker compose up -d db`, run migrations,
build the web app, and start the API — signup → upload resume → chat to find roles →
save the best ones.
