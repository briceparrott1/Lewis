# Lewis — Architecture & Stack Design

**Date:** 2026-08-06
**Status:** Architecture locked. Subsystem deep-dives (frontend, backend, agent core) pending.

## 1. Product summary

Lewis is an agent that automates finding job roles for a user. Inputs: the user's
**resume** and a **few sentences of free text** describing the roles they want
(e.g. "new grad, high-growth FDE roles in San Francisco"). The agent scans job
boards, filters and ranks against the resume, and returns matches the user can save.

## 2. Locked stack decisions

| Layer | Choice | Notes |
|---|---|---|
| Repo | Monorepo | pnpm workspace (JS) + `uv` (Python); plain folders, no Turborepo/Nx |
| Backend | FastAPI + LangGraph, Python 3.12 | `uv` for dependency management |
| Agent LLM | Claude `claude-sonnet-5` | Query understanding + resume-based ranking |
| Frontend | React + Vite + TypeScript | Signup, chat, saved-jobs views |
| Database | Postgres + SQLAlchemy 2.0 + Alembic | Migrations via Alembic |
| Auth | JWT access token; bcrypt/argon2 hash | Minimal, no refresh-token rotation in v1 |
| Resume ingestion | PDF/DOCX upload → server-side text extraction | `pypdf`, `python-docx` |
| Job sources | Greenhouse + Ashby public board APIs | No auth required |
| Company universe | Curated static seed list | Hand-curated board tokens; grows manually |
| Local dev | Docker Compose | `docker compose up` → api + web + postgres |
| Prod | Railway | api service + static web + managed Postgres |

## 3. Key architecture decisions & rationale

- **Synchronous, streamed-in-chat execution.** A chat turn runs the full
  scan→filter→rank inline and streams results back via SSE. Chosen for simplicity
  and fastest path to prod. The LangGraph run is written as a **pure callable**
  (prefs + resume in → ranked jobs out) with the HTTP layer as a thin wrapper, so a
  scheduled/background "automated daily agent" can reuse the same graph later
  without a rewrite.
- **Per-company board reality.** Greenhouse and Ashby expose only per-company job
  boards, not global search. v1 therefore scans a curated seed list of company board
  tokens and filters client-side.
  - Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{token}/jobs`
  - Ashby: `https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true`
- **Scan-all + short in-memory cache.** Every search scans all seed companies
  concurrently; a short-lived in-memory cache absorbs repeat scans. No persistent
  job cache table in v1.
- **Ephemeral chat.** No chat history persistence in v1 (no `chat_messages` table).
- **No `search_runs` table.** That belongs to the deferred async execution model.
- **Docker everywhere** keeps prod portable: the same images that run locally run on
  Railway, and could move to EC2/ECS/Fly later as a migration, not a rewrite.

## 4. Monorepo layout

```
lewis/
├─ apps/
│  ├─ api/                  # FastAPI + LangGraph
│  │  ├─ lewis_api/
│  │  │  ├─ main.py         # app + routes
│  │  │  ├─ auth/           # jwt, password hashing, deps
│  │  │  ├─ db/             # models, session, alembic migrations
│  │  │  ├─ agent/          # LangGraph graph, nodes, tools, state
│  │  │  ├─ sources/        # greenhouse.py, ashby.py, seed_companies.yaml
│  │  │  └─ routes/         # auth, chat, jobs
│  │  ├─ pyproject.toml
│  │  └─ Dockerfile
│  └─ web/                  # React + Vite + TS
│     ├─ src/               # signup, chat, saved-jobs
│     ├─ package.json
│     └─ Dockerfile
├─ packages/
│  └─ shared-types/         # optional: OpenAPI-generated TS types
├─ docker-compose.yml       # api + web + postgres
├─ pnpm-workspace.yaml
└─ README.md
```

## 5. Runtime architecture & request flow

```
React/Vite  ──JWT, REST + SSE──►  FastAPI (/auth /jobs /chat)
  signup                                │
  chat                                  ▼
  saved-jobs                    LangGraph run()  (pure callable: prefs → ranked)
                                        │ fan-out
                                        ▼
                               Greenhouse / Ashby board fetchers (public, no auth)
                                        │
                              SQLAlchemy ▼
                                    Postgres  (users, profiles, saved_jobs)
```

**Chat search turn:** user message → `/chat` (SSE) → `parse_query` → scan seed
companies' GH/Ashby boards concurrently → filter (location/level/keywords) → LLM
rank against resume → stream results into chat → user clicks Save → `saved_jobs` row.

## 6. Data model (v1)

- **users** — id, email, password_hash, created_at
- **user_profiles** — user_id, resume_text, raw_prefs_text, structured_prefs (jsonb)
- **saved_jobs** — id, user_id, source (`greenhouse`|`ashby`), company, title,
  location, url, raw (jsonb), saved_at

## 7. Agent graph shape (high-level; deep-dive pending)

`parse_query` → `plan_sources` → `fetch_boards` (fan-out over seed list) →
`normalize` → `filter` → `rank_with_resume` → `respond`.

State carries: user prefs, resume, candidate jobs, ranked results.
Tools: the two board fetchers + a scoring/ranking step.

## 8. Out of scope for v1 (explicitly deferred)

- Async/background execution and `search_runs`
- Scheduled "daily agent" cron runs (graph designed to allow it later)
- Persistent job cache and chat history
- Sources beyond Greenhouse + Ashby
- Refresh tokens, password reset, email verification
- Horizontal scale concerns

## 9. Next: subsystem deep-dives

1. **Agent core** — execution graph, node contracts, tool signatures, state schema,
   ranking prompt, error/timeout handling per board.
2. **Backend** — route contracts, auth flow, SSE protocol, DB session/migrations,
   config.
3. **Frontend** — signup flow, chat UI + SSE consumption, saved-jobs view, API client.
