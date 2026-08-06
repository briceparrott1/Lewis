# PRD — Backend

**Date:** 2026-08-06 · **Owner:** Brice Parrott · **Status:** Ready for planning
**Design reference:** [architecture spec §8](../superpowers/specs/2026-08-06-lewis-architecture-design.md)

## 1. Purpose

The backend is a single FastAPI service that authenticates users, stores their
profile and saved jobs, streams the agent's search results over SSE, and serves the
React SPA — all from one origin for minimal config and secure cookie auth.

## 2. Goals

- Minimal, secure auth (JWT in httpOnly cookie) that requires zero token handling in
  the frontend.
- Stream agent runs to the browser in real time.
- Persist users, profiles, saved jobs, and the served-jobs ledger.
- Ship to prod on Railway as one containerized service.

## 3. Non-goals (v1)

- Refresh tokens, password reset, email verification.
- Rate limiting, multi-region, horizontal scale.
- A separate web service / CORS setup (single origin instead).

## 4. User scenarios

1. New user signs up → cookie set → lands in onboarding.
2. Returning user with valid cookie → `GET /api/auth/me` succeeds → app loads.
3. User sends a chat message → SSE stream delivers status + ranked jobs live.
4. User saves a job → it appears in the saved-jobs list on refresh and on the saved
   screen.

## 5. Functional requirements

| # | Requirement |
|---|---|
| B1 | `POST /api/auth/signup` and `/login` validate credentials (argon2id), mint a 7-day JWT, set it as `HttpOnly; Secure; SameSite=Lax` cookie. |
| B2 | `POST /api/auth/logout` clears the cookie. `GET /api/auth/me` returns the user or 401. |
| B3 | An auth dependency reads+verifies the cookie on every protected route and injects `user_id`; missing/expired → 401. |
| B4 | `POST /api/profile/resume` accepts PDF/DOCX multipart, extracts text (`pypdf`/`python-docx`), stores **text only** (file discarded), returns `{resume_text}`. |
| B5 | `GET /api/profile` returns `{resume_text, prefs}`; `PUT /api/profile/prefs` stores `raw_prefs_text` (structuring is the agent's job). |
| B6 | `POST /api/chat` accepts `{message, conversation_id}`, derives `thread_id = user_id:conversation_id`, runs the agent graph, and returns an SSE `text/event-stream` of `status`/`clarify`/`result`/`done` frames. |
| B7 | `GET /api/jobs` lists saved jobs; `POST /api/jobs` saves a posted `RankedJob`; `DELETE /api/jobs/{id}` unsaves. All scoped to `user_id`. |
| B8 | On client disconnect (`request.is_disconnected()`), the graph task is cancelled; no partial `record_served`. |
| B9 | FastAPI serves the built SPA (catch-all → `index.html`) alongside `/api/*` under one origin. |
| B10 | App tables migrated via Alembic; `AsyncPostgresSaver.setup()` runs once in the lifespan. |
| B11 | Config via `pydantic-settings`: `DATABASE_URL`, `JWT_SECRET`, `ANTHROPIC_API_KEY`, `JWT_EXPIRE_DAYS`, `MAX_RESULTS`. |

## 6. Non-functional requirements

- **Security:** token unreadable by JS (httpOnly); `SameSite=Lax` mitigates CSRF;
  passwords argon2id; secrets only via env.
- **Streaming:** `status` events keep the SSE connection alive through long scans; no
  idle timeout on Railway.
- **DB access:** async SQLAlchemy 2.0, one `AsyncSession` per request.
- **Isolation:** every data access filtered by authenticated `user_id`.
- **Portability:** one Docker image; same image runs locally (compose) and on Railway.

## 7. Data model (see spec §6)

`users`, `user_profiles`, `saved_jobs`, `served_jobs` (app, Alembic-managed) +
LangGraph checkpoint tables (`setup()`-managed).

## 8. Acceptance criteria

- [ ] Signup then app reload keeps the user logged in (cookie persists) for 7 days.
- [ ] Protected routes return 401 without a valid cookie.
- [ ] Uploading a PDF resume returns extracted text; the raw file is not stored.
- [ ] `POST /api/chat` streams frames incrementally (verifiable via curl: frames
      arrive over time, not all at once).
- [ ] A clarify turn followed by a reply on the same `conversation_id` resumes the
      same graph run.
- [ ] Save then `GET /api/jobs` returns the job; delete removes it.
- [ ] A second user cannot read the first user's jobs or resume.
- [ ] The built SPA loads from the API origin and client-side routes resolve.

## 9. Dependencies

- Agent core (the graph it invokes).
- Postgres (app tables + checkpointer).
- Claude API key.
- Frontend build output (`dist`) available to serve in prod.

## 10. Open questions

- Cookie `Secure` must be conditional in local dev over HTTP vs prod HTTPS — confirm
  the dev/prod switch during implementation.
