# PRD — Agent Core

**Date:** 2026-08-06 · **Owner:** Brice Parrott · **Status:** Ready for planning
**Design reference:** [architecture spec §7](../superpowers/specs/2026-08-06-lewis-architecture-design.md)

## 1. Purpose

The agent core is the engine that turns a user's resume and free-text role
description into a short, ranked, non-repeating list of real job postings. It is the
product's core value: matching that reasons about tradeoffs the way the user would.

## 2. Goals

- Convert free-text preferences into structured, prioritized search criteria.
- Scan the curated Greenhouse + Ashby seed universe and return the best 5–7 matches.
- Rank against the user's resume and their stated priorities, making explicit
  tradeoffs (e.g. role over location).
- Never show the same job twice to a user.
- Ask a clarifying question when — and only when — the query is too thin to search.

## 3. Non-goals (v1)

- Background/scheduled runs (graph is built to allow it later; not wired now).
- Sources beyond Greenhouse + Ashby.
- Persisting conversation transcripts (chat is ephemeral).
- LLM-based re-crawling or discovery of new companies beyond the seed list.

## 4. User scenarios

1. **Clear query:** "New grad FDE roles in SF or remote" → agent returns 5–7 ranked
   FDE roles, each with a one-line, resume-aware reason.
2. **Vague query:** "I want a good tech job" → agent asks one targeted clarifying
   question, then searches after the reply.
3. **Tradeoff:** "FDE, and SF if possible" → a strong FDE role that is remote/NYC
   still surfaces and can out-rank a weak non-FDE role in SF.
4. **Repeat search:** running a similar query later surfaces the *next* batch, never
   jobs already shown.

## 5. Functional requirements

| # | Requirement |
|---|---|
| A1 | `parse_query` extracts and **merges across turns** a `StructuredPrefs` object incl. `role_keywords`, `locations`, `remote_ok`, `seniority`, `required[]`, `priorities[]`. |
| A2 | Sufficiency gate: proceed only if `role_keywords` present AND (`locations` non-empty OR `remote_ok is True`); otherwise ask one clarifying question. |
| A3 | At most **one** clarifying question per conversation; afterward proceed best-effort. No infinite loop. |
| A4 | Clarify pause/resume works across two separate HTTP requests via `interrupt()` + Postgres checkpointer keyed by `thread_id`. |
| A5 | `fetch_boards` scans **all** seed companies concurrently (semaphore ~15), per-board timeout ~5s, ~10min TTL cache, tolerant of partial failures (a failed board is skipped, not fatal). |
| A6 | `normalize` maps Greenhouse + Ashby postings to the common `Job` schema and dedupes. |
| A7 | `exclude_served` removes any job whose normalized-URL `job_key` is in the user's served set **before** ranking. |
| A8 | `prefilter` hard-filters only on `required[]`; soft-scores the rest weighted by `priorities` rank; passes top ~50 to the ranker. |
| A9 | `rank` scores candidates 0–100 with a one-line reason via Claude structured output, trading off by priority order. |
| A10 | `respond` streams only the top `MAX_RESULTS` (default 6, range 5–7), sorted by score. |
| A11 | `record_served` persists **only the shown** jobs' keys to `served_jobs` (permanent, `ON CONFLICT DO NOTHING`). |
| A12 | The graph is a **pure callable** (prefs + resume → ranked jobs), independent of the HTTP layer. |
| A13 | The graph emits typed streaming events: `status`, `clarify`, `result`, `done`. |

## 6. Non-functional requirements

- **Latency:** a typical scan completes in ~30s–2min; `status` events emitted
  throughout so no stretch exceeds a few seconds of silence.
- **Cost control:** ranker sees ≤ ~50 candidates; JDs truncated to ~2k chars.
- **Resilience:** any single board failing/timing out must not fail the run.
- **Determinism of no-repeat:** a job shown once is never shown again to that user.
- **Isolation:** one user can never resume or read another user's thread state.

## 7. Interfaces (see spec §7.3–7.8 for detail)

- **Input:** `user_id`, `resume_text`, `new_message`, prior `prefs`, `served_keys`.
- **Output stream:** `status{text}`, `clarify{question}`, `result{RankedJob}`,
  `done{count}`.
- **Persistence touched:** `served_jobs` (write), checkpointer tables (read/write),
  `user_profiles.structured_prefs` (updated as prefs are learned).

## 8. Acceptance criteria

- [ ] A vague query yields exactly one clarify event, then a normal result set on the
      follow-up message.
- [ ] A clear query returns 5–7 `result` events followed by one `done`.
- [ ] Re-running the same query never returns a previously shown job.
- [ ] Killing one seed board's endpoint (simulated timeout) still yields results.
- [ ] A `required` dimension (e.g. role) never appears violated in results; a
      non-required preference (e.g. location) may be traded off, and the reason
      reflects it.
- [ ] The graph can be invoked directly (no FastAPI) in a unit test and returns
      ranked jobs.

## 9. Dependencies

- Claude API (`claude-sonnet-5`) + `ANTHROPIC_API_KEY`.
- Postgres (checkpointer + `served_jobs`).
- `seed_companies.yaml` populated with valid Greenhouse/Ashby board tokens.
- Backend to supply auth-scoped `user_id`, resume, and prefs.

## 10. Open questions

- Seed list size/content for launch (target ~100–300 companies) — to be curated.
- Exact soft-score weighting formula by priority rank — tune during implementation.
