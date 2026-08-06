# PRD — Frontend

**Date:** 2026-08-06 · **Owner:** Brice Parrott · **Status:** Ready for planning
**Design reference:** [architecture spec §9](../superpowers/specs/2026-08-06-lewis-architecture-design.md)

## 1. Purpose

The frontend is a small React + Vite + TypeScript SPA (Tailwind) with three jobs:
get the user signed in and onboarded, let them search via a streaming chat, and let
them manage saved jobs. It holds no auth token (cookie-based) and renders the agent's
SSE stream live.

## 2. Goals

- Frictionless signup → resume upload → straight into searching.
- A chat that streams progress and job results in real time.
- Save/unsave jobs with instant, consistent UI across screens.
- Minimal, clean UI; fast to build and to prod.

## 3. Non-goals (v1)

- A separate preferences form (prefs are captured conversationally in chat).
- Rich profile editing, settings, notifications, or theming.
- Offline support, SSR, mobile-native.

## 4. User scenarios

1. **Signup → onboarding:** new user creates an account, is required to upload a
   resume once, then lands in chat.
2. **Search:** user types a role description; sees "Scanning…" then job cards appear
   one by one; saves the good ones.
3. **Clarify:** agent asks a question inline; user answers in the same box; results
   follow.
4. **Saved jobs:** user opens the saved view, reviews cards, unsaves one; it
   disappears immediately.

## 5. Functional requirements

| # | Requirement |
|---|---|
| F1 | Routes: `/signup`, `/login` (public), `/onboarding`, `/` (chat), `/saved` (authed). |
| F2 | On app load, a guard calls `GET /api/auth/me`: 401 → `/login`; authed w/o resume (`GET /api/profile`) → `/onboarding`; else → chat. |
| F3 | Signup/Login forms POST credentials, then invalidate the `me` query and redirect through the guard. |
| F4 | Onboarding: PDF/DOCX dropzone → `POST /api/profile/resume` (multipart) → redirect to chat on success. |
| F5 | Chat mints a `conversation_id` (uuid) on mount; a "New chat" control resets it. |
| F6 | Chat consumes SSE via `fetch` + `ReadableStream` (not `EventSource`), parsing `event:`/`data:` frames and dispatching to a `useReducer`. |
| F7 | Render per event: `status` → ephemeral line; `clarify` → agent bubble (answered in the same input, same `conversation_id`); `result` → `<JobCard>`; `done` → summary line. |
| F8 | `<JobCard>` shows title, company, location, score, one-line reason, apply link; has Save (chat) / Unsave (saved view). |
| F9 | Save POSTs the `RankedJob` payload it already holds; save/unsave mutations `invalidateQueries(["jobs"])` so both chat and saved views stay consistent. |
| F10 | Saved view lists `<JobCard>`s from `GET /api/jobs`. |
| F11 | React Query manages `me`/`profile`/`jobs`; `AuthContext` derives from the `me` query; chat stream is local state. |
| F12 | `AbortController` cancels an in-flight chat stream on unmount/navigation. |

## 6. Non-functional requirements

- **No token handling:** the app never reads/stores a JWT (httpOnly cookie); `fetch`
  uses `credentials: "include"`.
- **Perceived latency:** first `status` line renders within ~1s of sending a message.
- **Consistency:** saving/unsaving reflects everywhere without manual refetch.
- **Bundle:** keep dependencies minimal (Tailwind, React Query, React Router).
- **Dev ergonomics:** Vite dev server proxies `/api` → FastAPI for same-origin cookies.

## 7. Interfaces consumed

- `GET /api/auth/me`, `POST /api/auth/{signup,login,logout}`
- `GET /api/profile`, `POST /api/profile/resume`, `PUT /api/profile/prefs`
- `POST /api/chat` (SSE), `GET/POST /api/jobs`, `DELETE /api/jobs/{id}`

## 8. Acceptance criteria

- [ ] Fresh signup is forced through onboarding before reaching chat.
- [ ] A user with a resume skips onboarding on next login.
- [ ] Sending a message shows streaming status then job cards appearing incrementally.
- [ ] Answering a clarify question in the same chat continues the same search.
- [ ] Saving a job in chat makes it appear in `/saved` without a manual reload.
- [ ] Unsaving in `/saved` removes it immediately.
- [ ] Navigating away mid-stream cancels the request (no state leak / console errors).
- [ ] Reloading the page keeps the user logged in (cookie).

## 9. Dependencies

- Backend routes + SSE contract.
- Agent core streaming event shapes (`status`/`clarify`/`result`/`done`, `RankedJob`).
- Tailwind, TanStack React Query, React Router.

## 10. Open questions

- Minimal visual design/branding (logo, palette) — decide during build; Tailwind
  defaults are the starting point.
