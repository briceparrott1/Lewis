# UI/UX Overhaul — Navigation, Agent Behavior, Theme, Streaming — Design

**Date:** 2026-08-07
**Status:** Design approved. Ready for implementation planning.

## 1. Problem

Four separate but related UX gaps make the product feel unfinished:

1. **Navigation is a dead end.** There is no shared header/nav anywhere in
   `apps/web/src`. Onboarding auto-redirects to chat after resume upload
   (`Onboarding.tsx:37-38`), but there's no way back — chat has no link to
   revisit onboarding, and no logout control is wired up on the frontend even
   though the backend already exposes `POST /api/auth/logout`
   (`apps/api/lewis_api/auth/routes.py:59-60`).
2. **The agent never speaks first.** `Chat.tsx` mounts with an empty item
   list and does nothing until the user types (`Chat.tsx:21-33`). A blank
   text box with no prompt is a bad first impression.
3. **The agent ignores what the user actually said.** Any input that isn't
   yet "sufficient" (`prefs.py:48-51`) gets the exact same hardcoded
   `CLARIFY_TEXT` (`graph.py:20-23`) regardless of whether the user typed
   "hi" or a half-formed job description.
4. **Preferences don't survive anything.** `UserProfile.structured_prefs`
   (`models.py:22-31`) is a live DB column that is never read into the agent
   and never written back (`chat/routes.py:33` fetches it into `prior_prefs`
   then discards it, marked `# noqa: F841`). Preferences live only in the
   in-memory LangGraph checkpointer, keyed by a `thread_id` that changes
   every time the Chat component remounts or "New chat" is clicked
   (`Chat.tsx:24,71-74`). Nothing survives a reload, a new tab, or a new
   conversation.
5. **The visual design is default Tailwind with no intentional theme** — no
   `@theme` tokens, no component library, grayscale-plus-blue-links look
   throughout.
6. **Text isn't actually streamed.** The backend generates the full
   narrative/clarify reply in one non-streaming call and the frontend
   inserts it whole (`narrate.py:22-50`, `Chat.tsx:86-97`). This spec
   supersedes the "out of scope: token-by-token streaming" note in
   `2026-08-07-chat-narrative-redesign-design.md`.

## 2. Goals

- A user can get from any authenticated page to any other in one click.
- Chat opens with a message from Lewis, not a blank box.
- Lewis acknowledges what the user actually typed before asking for missing
  info — no more identical canned text regardless of input.
- Preferences persist per user across conversations, reloads, and restarts.
- A deliberate, chat-first visual theme applied consistently across the app.
- User-facing LLM text (clarify replies, narrative results) streams in as
  it's generated instead of appearing all at once.

## 3. Non-goals

- No dedicated preferences/settings page — preferences are viewed and
  changed conversationally only (confirmed with user).
- No chat history persistence beyond what's needed for prefs continuity —
  past message transcripts remain ephemeral per the existing architecture.
- No visual rebrand of the *product identity* (name/logo) — this is about
  layout, color, and spacing tokens, not a new brand.
- Not copying Anthropic's actual brand assets/exact palette — the theme
  takes stylistic cues from the "clean single-column AI chat" genre
  (whitespace, one accent color, rounded bubbles) using an original palette,
  to avoid brand/trademark overlap.

## 4. Sequencing

Four phases, each independently shippable and tested before the next
starts: **Nav → Agent behavior/prefs → Theme → Streaming**. Rationale: nav
is small and unlocks navigating to review the rest of the work; the
behavior/persistence fix is the core functional gap and touches backend
data flow, so it should land before the visual layer is rebuilt on top of
it; theme is pure styling once page structure is settled; streaming is
polish with the lowest risk, done last.

---

## 5. Phase 1 — Navigation & app shell

### 5.1 `AppLayout` component
New `apps/web/src/components/AppLayout.tsx`: renders a persistent header
(Lewis wordmark linking to `/`, nav links for **Chat** and **Saved**, a link
to **Profile** → `/onboarding`, and **Logout**) above an `<Outlet />`.

### 5.2 Routing
`App.tsx` restructures the three authenticated routes (`/`, `/saved`,
`/onboarding`) to render under one layout route wrapping `RequireAuth` +
`AppLayout`, instead of each page independently rendering its own top-level
wrapper. `RequireResume` continues to gate `/` specifically.

### 5.3 Logout
`useAuth()` (`auth.tsx`) gains a `logout()` method: `POST /api/auth/logout`,
then invalidate the `["me"]` query. Header's Logout button calls it and
navigates to `/login`.

### 5.4 Onboarding reachability
Onboarding keeps its existing auto-redirect to `/` after a successful resume
upload. It becomes reachable again afterward via the header's Profile link,
so a user can revisit it to re-upload a résumé. No change to the upload
form itself.

---

## 6. Phase 2 — Agent behavior & persistent preferences

### 6.1 Persisting `structured_prefs`
- `chat/routes.py`: the already-fetched `prior_prefs` (currently discarded)
  is passed into `run_agent`'s `inputs` as the starting `prefs` value for
  the graph (`graph.py` inputs construction, `~graph.py:123-129`).
- After `run_agent` completes, the route writes the graph's final `prefs`
  state back to `UserProfile.structured_prefs` and commits. This makes
  prefs durable across "New chat," reloads, and process restarts —
  independent of the `MemorySaver` checkpointer's lifetime.
- `AgentState`/`parse_prefs` already merges newly-extracted fields into
  existing `prefs` (`prefs.py`) rather than overwriting, so seeding from the
  DB and merging in new turns composes correctly.

### 6.2 Natural clarify replies (smalltalk handling)
- New `agent/clarify.py::generate_clarify_reply(user_message, prefs, missing_fields, llm) -> str`
  — a focused Haiku call (same pattern as `narrate.py`'s `narrate_results`)
  that takes what the user actually typed plus which fields are still
  missing (the same `role_keywords` / `locations`-or-`remote_ok` signals
  `is_sufficient` already checks, `prefs.py:48-51`), and returns a short
  natural reply that acknowledges the input before asking for what's
  missing. Replaces the static `CLARIFY_TEXT` constant.
- Kept as its own call rather than folding into `parse_prefs`'s extraction
  schema, to keep extraction (structured, deterministic-ish) and response
  generation (natural language) separately testable, matching the existing
  `narrate.py` separation.
- **LLM failure:** falls back to the current static `CLARIFY_TEXT`, same
  fail-open pattern as `narrate_results`'s templated fallback — a clarify
  turn must never error out.

### 6.3 Agent-initiated first message
- No backend/graph involvement — rendered client-side in `Chat.tsx` from a
  template when the item list is empty on mount, using the already-fetched
  `Profile` (`useProfile()`, `queries.ts:6`), which includes
  `structured_prefs`.
- Returning user with stored prefs: summarize them and ask if they still
  apply (e.g. "Last time you were looking for {roles} in {locations} —
  still the plan, or has something changed?").
- New/no-prefs user: a short prompt naming what to do ("Tell me what kind of
  role you're looking for — location, seniority, anything that matters to
  you.").
- No LLM call for this message — template-only, per cost-conscious default
  and because it doesn't need generation (the same reasoning `narrate.py`'s
  empty-results canned message already uses).

---

## 7. Phase 3 — Visual theme

### 7.1 Design tokens
`apps/web/src/index.css` gains a Tailwind v4 `@theme` block: background,
surface, text-primary/secondary, one accent color, border, and
success/error status colors, plus a radius and shadow scale. Chat-first
minimal style: generous whitespace, rounded message bubbles, soft shadows,
single accent used sparingly (primary actions, active nav link, user
bubble).

### 7.2 Applied surfaces
Restyle using the new tokens (utility classes only — no component library
added, keeping the existing hand-rolled Tailwind approach):
`AppLayout` header, `Chat.tsx` message bubbles and input, `CompactJobRow.tsx`
/ `JobCard.tsx`, `Spinner.tsx`, `Login.tsx` / `Signup.tsx` forms, `Saved.tsx`.

---

## 8. Phase 4 — Real token streaming

### 8.1 Backend
- `llm.py`: add `LLM.stream(system, user) -> AsyncIterator[str]` alongside
  the existing `complete()`, using the Anthropic streaming API
  (`client.messages.stream(...)`), yielding text deltas.
- `narrate.py` and the new `clarify.py` (Phase 2) both switch to
  `llm.stream(...)`.
- `graph.py`: the `respond`/`clarify` nodes call `writer(...)` once per
  delta instead of once with the full string. New SSE event
  `{"type": "narrative_delta", "text": str}` (and equivalently
  `clarify_delta`) per chunk, sent while the stream is in progress. Once the
  stream finishes, the existing `{"type": "narrative", "text": str}` /
  `{"type": "clarify", "text": str}` event is still sent exactly as today,
  but now carrying the full accumulated text as both a completion signal
  (frontend knows this message is done) and a safety net (reconciles the
  displayed text to the authoritative full string in case any delta was
  dropped in transit) — no new completion event type needed.

### 8.2 Frontend
- `sse.ts` / `types.ts`: add the `narrative_delta` / `clarify_delta` event
  types to `ChatEvent`.
- `Chat.tsx` reducer: on a delta event, append text to the current
  in-progress assistant message item (creating it on the first delta); on
  the existing `narrative`/`clarify` event, set that item's text to the
  event's full string (reconciling any dropped deltas) and mark it
  finalized.

### 8.3 Fallback
If a stream errors mid-flight (same class of failure Phase 2's clarify
fallback already handles for non-streaming), the turn falls back to the
templated message, sent as a single non-streamed event — consistent with
existing fail-open handling elsewhere in the graph.

---

## 9. Testing

**Backend (per phase):**
- Phase 2: `test_chat.py`/`test_graph.py` — prefs seeded from DB profile
  flow into graph inputs; final prefs written back after a turn; a second
  turn (simulating "New chat") starts with the previously-saved prefs.
  New `test_clarify.py`: `generate_clarify_reply` happy path (mocked LLM,
  asserts prompt includes user message + missing fields) and LLM-failure →
  static fallback.
- Phase 4: `narrate_results`/`generate_clarify_reply` streaming variants
  (mocked streaming client) assert deltas are yielded and concatenate to
  the same text `complete()` would have produced; SSE delta event shape
  test in `test_chat.py`.

**Frontend (per phase):**
- Phase 1: routing test — authenticated pages render inside the shared
  layout; logout clears the `me` query and redirects; onboarding reachable
  from chat.
- Phase 2: `Chat.test.tsx` — first render shows the templated greeting
  (new-user and returning-user-with-prefs variants); no LLM/network call
  fired for it.
- Phase 4: reducer test — sequential delta events append into one message
  item; completion marker finalizes it.

## 10. Out of scope

- Dedicated preferences/settings UI (conversational only, per Non-goals).
- Persistent chat history/transcript beyond prefs continuity.
- Any new frontend dependency (icon library, component library, animation
  library) — theme and streaming reveal stay CSS/plain-React, consistent
  with the existing minimal-deps frontend.
