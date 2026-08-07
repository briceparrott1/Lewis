# Chat UX Redesign — Loading Feedback & Narrative Results — Design

**Date:** 2026-08-07
**Status:** Design approved. Ready for implementation planning.

## 1. Problem

Today the chat turn (`/api/chat`, SSE) gives the user two static status lines
("Scanning N companies…", "Ranking N matches…") and then dumps the ranked
jobs as a flat list of `JobCard`s. It doesn't feel like the agent is actively
working, and the results read like a database query, not a helpful answer.

## 2. Goals

- Make the wait feel actively worked-on, using research-backed timing rather
  than an arbitrary interval.
- Replace the job-card list with an LLM-written narrative paragraph (using
  the user's name) followed by a compact, still-actionable job list.
- Keep cost bounded: skip the narrative LLM call when there are no results.

## 3. Backend changes

### 3.1 `UserProfile.name`
New nullable `name: str | None` column on `UserProfile` (Alembic migration).
Collected via a new field on the onboarding form, alongside resume upload.
Chat route already loads `UserProfile` for the current turn — no extra query.

### 3.2 Granular real status events
`AgentState`/graph nodes emit ~5 status events tied to actual phases (up from
2 today), via `get_stream_writer()`:
1. `parse` node: "Reading your resume and preferences…"
2. `search` node start: "Scanning N companies for openings…"
3. after prefilter: "Filtering to your criteria…"
4. before `rank_jobs`: "Ranking matches against your profile…"
5. before narrative: "Writing up what I found…"

### 3.3 Narrative generation
New `agent/narrate.py::narrate_results(ranked, prefs, resume_text, user_name, llm) -> str`.

- Requires a free-text completion. Add `LLM.complete(system, user) -> str` to
  the `LLM` protocol (today `AnthropicLLM` only exposes forced-tool-use
  `.structured()`). `AnthropicLLM.complete()` reuses the same shared client
  instance — same pattern as `parse_prefs` + `rank_jobs` already sharing one
  `llm` across a run.
- Called from the `respond` node, after `ranked` is trimmed to `max_results`.
- Emits one new SSE event: `{"type": "narrative", "text": str}`, sent
  **before** the existing per-job `result` events, so the prose headline
  arrives first and the compact list fills in below it.
- **Empty results:** if `ranked` is empty, skip the LLM call entirely and use
  a canned message (e.g. "I didn't find any roles matching that this time —
  try broadening your criteria."). Also closes the pre-existing "Empty-State
  UX" gap noted in `status.md`.
- **LLM failure:** catch exceptions from `LLM.complete()` and fall back to a
  templated sentence ("I found {n} jobs matching your search.") — the turn
  must always complete with `narrative` + `done`, never error out on this
  step.

### 3.4 Event schema (additions)
```
{"type": "narrative", "text": str}   # new
```
`result` and `done` events are unchanged in shape; `status` events simply
occur more often and with different text.

## 4. Frontend changes

### 4.1 `Spinner` component
CSS-only (no new dependency), shown next to the status text while `busy`.

### 4.2 Status ticker (`useStatusTicker` hook)
Backed by research (Nielsen Norman Group response-time thresholds; Buell &
Norton's "labor illusion" / operational transparency findings — specific,
real activity descriptions measurably improve perceived wait and trust more
than a generic spinner):

- Real `status` events always win: shown immediately on arrival, timer
  resets.
- If no real event arrives within the swap window, the ticker rotates in a
  themed filler phrase (e.g. "Sifting through job boards…", "Reticulating
  listings…") from a fixed list, never repeating the same one twice in a
  row.
- Parameters: **minimum visible time 1.5–2s** per message; **target swap
  interval 2–3s**; **~1s cooldown** after a real event before a filler is
  allowed (avoids whiplash right after real text changes).
- The first visible message and the last message before results arrive are
  **always real** — filler never opens or closes the sequence. Before the
  first real backend event lands, show a neutral placeholder ("Getting
  started…"), not a filler phrase.
- Ticker stops immediately when `narrative` arrives — no trailing filler.

### 4.3 Results rendering
Chat reducer gains a `narrative` item kind. On `narrative`: render the prose
paragraph prominently, followed by a compact job list built from `result`
events (new lightweight row component — title/company/link/save — not the
full `JobCard`, which stays as-is for the Saved page). The old plain "Found N
roles." line is removed; the narrative (real or backend's templated
fallback) covers that now.

**Safety net:** if `done` arrives without a preceding `narrative` (e.g.
dropped mid-stream), fall back to a plain "Found N roles" line built from
`done.count`.

### 4.4 Onboarding
Add a `name` text input near the resume upload, wired to the new
`UserProfile.name` column.

## 5. Testing

**Backend:**
- Loosen `test_graph.py` status-event assertions (exact-count checks →
  "at least these phases occurred") to tolerate 2 → 5 status events.
- New tests: `narrate_results` happy path (mocked `LLM.complete`, asserts
  prompt includes name/jobs/resume/prefs); empty-`ranked` skips the LLM call;
  `LLM.complete` raising → templated fallback, turn still completes.
- `test_chat.py`: assert new `narrative` SSE event shape.
- Onboarding endpoint test: `name` persists to `UserProfile`.

**Frontend:**
- New `Chat.test.tsx` (doesn't exist today — real gap): spinner visible while
  busy, ticker shows real text immediately on event, narrative renders,
  compact job list renders with working save action, empty-results narrative
  renders.
- `useStatusTicker` unit test (fake timers): minimum display duration,
  interval bounds, first/last-always-real rule, cooldown after real events.
- Update/add `Onboarding.test.tsx` for the `name` field.

## 6. Out of scope

- Chat history persistence (still ephemeral per existing architecture).
- Streaming the narrative token-by-token (single `narrative` event, not
  incremental).
- Icon library — spinner stays CSS-only per existing minimal-deps frontend.
