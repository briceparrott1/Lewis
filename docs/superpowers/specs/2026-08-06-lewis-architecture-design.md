# Lewis — Architecture & Stack Design

**Date:** 2026-08-06
**Status:** Design complete — stack, architecture, and all three subsystem deep-dives
(agent core, backend, frontend) locked. Ready for implementation planning.

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
| Agent LLM | Claude, default `claude-haiku-4-5` (env `AGENT_MODEL`) | Query understanding + resume ranking; cheap by default, upgradeable |
| Frontend | React + Vite + TypeScript | Signup, chat, saved-jobs views |
| Database | Postgres + SQLAlchemy 2.0 + Alembic | Migrations via Alembic |
| Auth | JWT in httpOnly cookie; argon2id hash; 7-day expiry | Single-origin, no refresh token in v1 |
| Resume ingestion | PDF/DOCX upload → server-side text extraction | `pypdf`, `python-docx` |
| Job sources | Greenhouse + Ashby public board APIs | No auth required |
| Company universe | Curated static seed list | Hand-curated board tokens; grows manually |
| Local dev | Docker Compose | `docker compose up` → api + web + postgres |
| Prod | Railway | Single service: FastAPI serves SPA + `/api`, managed Postgres |

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
React/Vite  ──cookie JWT, REST + SSE──►  FastAPI (serves SPA + /api/*)
  signup                                    │
  chat                                      ▼
  saved-jobs                        LangGraph run()  (pure callable: prefs → ranked)
                                            │ fan-out
                                            ▼
                                   Greenhouse / Ashby board fetchers (public, no auth)
                                            │
                                  SQLAlchemy ▼
                            Postgres  (users, profiles, saved_jobs, served_jobs
                                       + LangGraph checkpoint tables)
```

**Chat search turn:** user message → `/chat` (SSE) → `parse_query` → scan seed
companies' GH/Ashby boards concurrently → filter (location/level/keywords) → LLM
rank against resume → stream results into chat → user clicks Save → `saved_jobs` row.

## 6. Data model (v1)

- **users** — id, email, password_hash, created_at
- **user_profiles** — user_id, resume_text, raw_prefs_text, structured_prefs (jsonb)
- **saved_jobs** — id, user_id, source (`greenhouse`|`ashby`), company, title,
  location, url, raw (jsonb), saved_at
- **served_jobs** — user_id, job_key (**normalized posting URL**), source_id
  (`{source}:{board_token}:{external_id}`, nullable backstop), served_at,
  `UNIQUE(user_id, job_key)`, index on user_id. Ledger of jobs already shown to a
  user, so future searches never repeat them (permanent, no re-surface).
  - `job_key` derives from the URL the APIs already return — Greenhouse
    `absolute_url`, Ashby `jobUrl` (not `applyUrl`). No browser needed.
  - **URL normalization** (before use as key): force `https`, lowercase scheme+host,
    strip query + `#fragment` (id lives in the path for both sources; also drops
    `utm_*`/`gh_src`), strip trailing slash.
  - `source_id` is kept as a backstop against Greenhouse host drift
    (`boards.` vs `job-boards.greenhouse.io`).
- **LangGraph checkpointer tables** — managed by `AsyncPostgresSaver`, separate from
  app tables; hold transient graph state per conversation `thread_id`.

`structured_prefs` (jsonb) shape:

```python
class StructuredPrefs(TypedDict, total=False):
    role_keywords: list[str]
    locations: list[str]
    remote_ok: bool | None
    seniority: Literal["intern","new_grad","mid","senior","staff"] | None
    extra: str
    required: list[str]     # hard-filter dimensions, e.g. ["role"]
    priorities: list[str]   # ordered soft prefs, most important first
```

## 7. Agent core — detailed design

### 7.1 Execution model

- Synchronous per chat turn, streamed via SSE. The graph is a **pure callable**
  wrapped by the HTTP layer.
- **Clarify-then-search loop:** if a query lacks enough signal, the graph asks one
  targeted clarifying question and pauses (LangGraph `interrupt()` + Postgres
  checkpointer), resuming on the user's next message. At most **one** clarify per
  conversation, then it proceeds best-effort — no infinite loop.

### 7.2 Graph topology

```
ingest → parse_query → ⟨route_sufficiency⟩
                          ├─ insufficient & not clarified → ask_clarify (interrupt, turn ends)
                          └─ else → plan_sources → fetch_boards → normalize
                               → exclude_served → prefilter → rank → respond → record_served
```

### 7.3 Nodes

| Node | Responsibility |
|---|---|
| `ingest` | Load resume + prior merged prefs (checkpoint) + user's `served_keys` set. |
| `parse_query` | Claude extracts/merges `StructuredPrefs` incl. `required` + `priorities`. |
| `route_sufficiency` | Conditional edge. Sufficient = `role_keywords` present AND (`locations` non-empty OR `remote_ok is True`). Priority conflicts can also trigger clarify. |
| `ask_clarify` | Emit one targeted question; `interrupt()`; set `clarified_once=True`. |
| `plan_sources` | Select boards from seed list (v1: all). |
| `fetch_boards` | Concurrent GH+Ashby fetch, semaphore ~15, per-board ~5s timeout, TTL cache ~10min, partial-failure tolerant. |
| `normalize` | Map raw postings → common `Job` schema; dedupe. |
| `exclude_served` | Drop jobs whose normalized-URL `job_key` ∈ user's served set. |
| `prefilter` | Hard-filter on `required` only; soft-score the rest weighted by `priorities` rank; take top ~50. |
| `rank` | Claude scores the ~50 candidates 0-100 + one-line reason vs resume/prefs, trading off by priority order. |
| `respond` | Sort by score; stream top `MAX_RESULTS` (default 6, range 5-7). |
| `record_served` | Insert the shown jobs' keys into `served_jobs` (`ON CONFLICT DO NOTHING`). |

### 7.4 State schema

```python
class AgentState(TypedDict):
    user_id: str
    resume_text: str
    prefs: StructuredPrefs          # merges across turns
    clarified_once: bool
    served_keys: set[str]
    new_message: str
    raw_postings: list[dict]
    candidates: list[Job]           # post-prefilter
    ranked: list[RankedJob]         # final, sorted
```

### 7.5 Common Job schema (normalization target; backend + frontend consume this)

```python
class Job(TypedDict):
    source: Literal["greenhouse","ashby"]
    company: str
    board_token: str
    external_id: str
    title: str
    location: str
    department: str | None
    url: str
    posted_at: str | None
    compensation: str | None        # Ashby sometimes provides
    description: str                # truncated to ~2k chars for ranking

class RankedJob(Job):
    score: int                      # 0-100
    reason: str                     # one line, resume- and priority-aware
```

### 7.6 Funnel knobs

| Knob | Value |
|---|---|
| Candidate cap into ranker | ~50 |
| Final shown to user (`MAX_RESULTS`) | 6 (configurable 5-7) |
| JD truncation for ranking | ~2k chars |
| Per-board fetch timeout | ~5s |
| Fetch concurrency | ~15 |
| Board cache TTL | ~10 min |

### 7.7 Streaming contract (agent → backend → SSE → frontend)

| event | payload | when |
|---|---|---|
| `status` | `{text}` | progress ticks ("Scanning 210 companies…") |
| `clarify` | `{question}` | clarify gate fires |
| `result` | `RankedJob` | each of the top `MAX_RESULTS` as ranking completes |
| `done` | `{count}` | end of turn |

### 7.8 Sources

- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`
  - Field map: `absolute_url`→url, `id`→external_id, `location.name`→location,
    `title`, `updated_at`→posted_at, `content`→description (HTML, strip to text).
- Ashby: `https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true`
  - Field map: `jobUrl`→url, `id`→external_id, `location`, `title`,
    `department`, `publishedAt`→posted_at, `descriptionPlain`→description
    (already plain text), `compensation`→compensation.
- Seed list of `{company, source, board_token}` in `sources/seed_companies.yaml`.
- Verified live (2026-08-06): both APIs return the posting URL and full
  description in the JSON with no auth — confirming URL-based `job_key` is in scope.

## 8. Backend — detailed design

### 8.1 Deployment & origin model

Single origin: FastAPI serves **both** the built React SPA and the `/api/*` routes
under one domain. Routers own `/api/*`; a catch-all returns `index.html` for
client-side routing. Dev preserves same-origin via Vite's proxy (`/api` → FastAPI).
One Railway service, one multi-stage Dockerfile (build React → copy `dist` into the
API image). Consequence: **no CORS** and first-party cookies.

### 8.2 Auth

- **JWT in an httpOnly, Secure, SameSite=Lax cookie.** The token is a signed JWT
  (`{sub: user_id, exp: now+7d}`); the browser stores and auto-attaches it; JS cannot
  read it (XSS-safe). "Bearer vs cookie" is only *transport* — same JWT, carried in a
  cookie instead of an `Authorization` header.
- **argon2id** password hashing (`argon2-cffi`).
- **7-day expiry, no refresh token.** On expiry the user logs in again.
- **CSRF:** neutralized by `SameSite=Lax` (blocks the cookie on cross-site POSTs).
- A FastAPI dependency reads the cookie, verifies signature+expiry, injects the
  current user; missing/expired → 401 → frontend routes to login.

E2E: signup/login → server sets `Set-Cookie: access_token=<JWT>; HttpOnly; Secure;
SameSite=Lax; Max-Age=604800` → every later request (incl. the `/api/chat` POST)
carries the cookie automatically → auth dependency yields `user_id`, which scopes the
agent run's resume/prefs/served-jobs.

### 8.3 Route contracts (under `/api`)

| Method + path | Body / params | Returns |
|---|---|---|
| `POST /api/auth/signup` | `{email, password}` | sets cookie, `{user}` |
| `POST /api/auth/login` | `{email, password}` | sets cookie, `{user}` |
| `POST /api/auth/logout` | — | clears cookie |
| `GET /api/auth/me` | (cookie) | `{user}` or 401 |
| `GET /api/profile` | (cookie) | `{resume_text, prefs}` |
| `POST /api/profile/resume` | multipart file (PDF/DOCX) | parse → store text → `{resume_text}` |
| `PUT /api/profile/prefs` | `{raw_prefs_text}` | store → `{prefs}` |
| `POST /api/chat` | `{message, conversation_id}` | **SSE stream** |
| `GET /api/jobs` | (cookie) | `[SavedJob]` |
| `POST /api/jobs` | `RankedJob` payload | save → `{saved_job}` |
| `DELETE /api/jobs/{id}` | — | unsave |
| `GET /api/health` | — | `{status}` |

Resolved judgment calls: resume stored as **extracted text only** (uploaded file
discarded); saving a job = client **POSTs the `RankedJob` payload** it already has
(no server re-fetch); prefs submitted as **`raw_prefs_text`** and structured by the
**agent** during `parse_query` (single source of truth for parsing).

### 8.4 SSE streaming (`POST /api/chat`)

- `StreamingResponse`, `media_type="text/event-stream"`; frames as
  `event: <type>\ndata: <json>\n\n` (types: `status`/`clarify`/`result`/`done`).
- `/chat` is a **POST with a body**, so the client uses **`fetch()` + a
  `ReadableStream` reader**, not native `EventSource` (GET-only). Cookie rides on the
  POST automatically.
- Backend runs the graph via `astream`, translating node emissions into frames.
- **`status` events double as keep-alive** through a 30s–2min scan (no idle timeout).
- **Disconnect:** on `request.is_disconnected()` cancel the graph task; checkpointer
  keeps last committed state; `record_served` only fires on completion, so an
  abandoned run serves nothing.

### 8.5 Conversation threads

- Client generates a `conversation_id` (uuid) per chat, sends it every message.
- Server derives **`thread_id = f"{user_id}:{conversation_id}"`** — namespaced by the
  authenticated user so no one can resume another user's thread.
- Same `conversation_id` → checkpointer resumes the interrupted graph (clarify
  answer); new chat → new id → fresh run.

### 8.6 DB, sessions, migrations, checkpointer

- **Async SQLAlchemy 2.0** (`asyncpg`), `async_sessionmaker`; a dependency yields one
  `AsyncSession` per request.
- **Alembic** migrates *app* tables (`users`, `user_profiles`, `saved_jobs`,
  `served_jobs`).
- **LangGraph `AsyncPostgresSaver`** on the same Postgres, manages its own checkpoint
  tables; `await checkpointer.setup()` runs once in the FastAPI **lifespan**. Two
  layers, one DB; we never hand-migrate the checkpoint tables.

### 8.7 Config

`pydantic-settings`, env-driven: `DATABASE_URL`, `JWT_SECRET`, `ANTHROPIC_API_KEY`,
`JWT_EXPIRE_DAYS=7`, `MAX_RESULTS=6`. `.env` locally, Railway env vars in prod.

### 8.8 Startup (lifespan)

Init DB engine → `await checkpointer.setup()` → load `seed_companies.yaml` into
memory → mount routers + SPA catch-all.

## 9. Frontend — detailed design

React + Vite + TypeScript, **Tailwind CSS**. Built to `dist`, served by FastAPI
(single origin). Dev: Vite `:5173` with `/api` proxy → FastAPI `:8000`.

### 9.1 Routing (React Router)

| Route | Access | Purpose |
|---|---|---|
| `/signup`, `/login` | public | email + password forms |
| `/onboarding` | authed, until resume exists | one-time resume upload |
| `/` (chat) | authed + resume present | main chat/search view |
| `/saved` | authed | saved jobs list |

**Guard on app load:** call `GET /api/auth/me` → 401 → `/login`; authed but no resume
(`GET /api/profile`) → `/onboarding`; else → chat. Wrappers: `<RequireAuth>`,
`<RequireResume>`.

### 9.2 Onboarding

Resume gate: after signup, a one-time required PDF/DOCX upload
(`POST /api/profile/resume`, multipart) → redirect to chat. **Role preferences are
NOT a form** — they're captured conversationally in chat and persisted to the profile
as the agent structures them (matches the NL-elicited priority model).

### 9.3 State management

- **TanStack React Query** for server state: `me`, `profile`, `jobs`.
  - `useQuery(["jobs"])` etc. handle loading/error/caching.
  - **Mutations** (save/unsave) call `invalidateQueries(["jobs"])` so the saved list
    refreshes on both the chat and saved screens automatically — the one real
    cross-screen data flow. Login/logout `invalidate(["me"])`.
- **`AuthContext`** derived from the `me` query (token is an httpOnly cookie, so auth
  state = "does `/me` succeed").
- **Chat stream** is NOT server state — a live SSE feed held in a `useReducer` in the
  chat page (messages + streaming status).

### 9.4 Screens

1. **Signup / Login** — form → POST → invalidate `me` → redirect through guard.
2. **Onboarding** — PDF/DOCX dropzone → upload → redirect to chat.
3. **Chat** — message list + input. `conversation_id` (uuid) minted on mount; "New
   chat" resets it. Renders SSE events: `status` → ephemeral gray line; `clarify` →
   agent bubble (user answers in the same box, same `conversation_id` → resumes
   thread); `result` → `<JobCard>` with Save; `done` → "Found N roles".
4. **Saved jobs** — list of `<JobCard>` from `GET /api/jobs`, each with Unsave
   (`DELETE`).

### 9.5 Chat SSE consumption

`streamChat(message, conversationId, onEvent)`: `fetch("/api/chat", {method:"POST",
body})` → `res.body.getReader()` → decode chunks, buffer, split on blank lines, parse
each `event:`/`data:` frame → dispatch to reducer. `AbortController` cancels on
unmount/navigation. (Native `EventSource` is unusable — it is GET-only.)

### 9.6 Shared

- **`<JobCard>`** — used in chat results and saved view: title, company, location,
  score, one-line reason, apply link (`url`), Save/Unsave. Save POSTs the `RankedJob`
  payload it already holds.
- **`api.ts`** — thin fetch wrapper, base `/api`, `credentials: "include"`, JSON
  helpers; React Query hooks wrap it.

## 10. Out of scope for v1 (explicitly deferred)

- Async/background execution and `search_runs`
- Scheduled "daily agent" cron runs (graph designed to allow it later)
- Persistent job cache and chat history
- Sources beyond Greenhouse + Ashby
- Refresh tokens, password reset, email verification
- Horizontal scale concerns

## 11. Design status

All three subsystem deep-dives complete:

1. ~~**Agent core**~~ — DONE (section 7).
2. ~~**Backend**~~ — DONE (section 8).
3. ~~**Frontend**~~ — DONE (section 9).

Next step: turn this design into an implementation plan (writing-plans).
