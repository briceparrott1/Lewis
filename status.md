# Lewis — Project Status

**As of 2026-08-08** | Repo: https://github.com/briceparrott1/Lewis | Branch: `main`

## 🔵 Open PR — Needs Your Merge Decision

**Job quality: ranking fixes + seed-list scaling**, branch `worktree-job-quality-ranking`, worktree at `.claude/worktrees/job-quality-ranking`.

Built via brainstorm (paused pending the UI/UX overhaul merge, then resumed with full autonomy per your instruction) → spec (`docs/superpowers/specs/2026-08-07-job-quality-wants-to-see-design.md`) → plan (`docs/superpowers/plans/2026-08-08-job-quality-ranking.md`, 5 tasks) → subagent-driven implementation → per-task reviews → final whole-branch review (opus) → one fix wave → clean:

1. **Fetch throughput** — `boards.py` concurrency raised 15→40; rate-limited (429) boards now log distinctly instead of looking identical to "0 matching jobs."
2. **Ranking bug fix** — `rank_jobs` used to silently default any candidate the LLM omitted from its response into results with `score=0, reason=""`; those could reach a user's final batch with an empty reason if the eligible pool was thin. Now dropped at the source.
3. **Prefilter robustness** — role-keyword matching now normalizes hyphens/whitespace (`"full stack"` now matches `"Full-Stack Engineer"` and vice versa) — this filter is a hard, unrecoverable gate, so a phrasing mismatch used to silently exclude good jobs.
4. **Industry diversity cap** — extends the existing company/seniority-tier caps (from the prior seniority-diversity PR) with a third axis: a static per-company `industry` tag (fixed 17-value taxonomy, not a live LLM guess) and a matching cap in `select_results.py`, generalizing "diversity" beyond company-only clustering. `industry="unknown"` stays uncapped, same pattern as seniority's "unknown" handling.
5. **Seed list scaled 106 → 252** — live-validated (real HTTP 200 + non-empty job list) against actual Greenhouse/Ashby endpoints, every entry industry-tagged. Honest shortfall from the 300+ aspiration: many well-known companies (Netflix, Shopify, HubSpot, CrowdStrike, HashiCorp, etc.) confirmed not to be on Greenhouse/Ashby at all (404s), not a scripting bug — see `apps/api/scripts/validate_seed_companies.py` (rerunnable) and its report in the PR.

**Verification:** 91/91 backend tests, ruff/black clean. Final whole-branch review caught one integration-level risk invisible to any single task's review: scaling the company pool 2.4x without also scaling `prefilter.py`'s candidate cap (still 50) meant the ranker was effectively only ever seeing an alphabetically-clustered slice of the pool (companies A–C), undercutting both the seed-list expansion and the new industry-diversity cap. Fixed: cap raised to 150, plus the `respond` funnel log now includes candidate count for future diagnosability.

**Deliberately deferred (not in this PR — see design doc's "Explicitly deferred" section and the final review's recommendations)**:
- Prefilter tie-break/backfill logic for thin diversity-capped batches (raising the cap is a mitigation, not a full fix — the underlying alphabetical-tie-break bias and the industry cap's lack of a backfill pass for thin survivor pools are real, named, and better as a focused follow-up with its own tests).
- Full qualification/desire preference field taxonomy from the original brainstorm (beyond role/location/seniority).
- Hard/soft preference ambiguity confirmation node.
- Dedup resurfacing policy (does a shown-but-ignored job ever come back — currently: no, permanent exclusion via `served_keys`).

**A handful of Minor findings were deliberately deferred** (see `.superpowers/sdd/2026-08-08-job-quality-ranking/progress.md` in that worktree for the full ledger before it's deleted): a dead defensive None-check in `boards.py`, missing branch-coverage for two logging paths, a naming-collision note between two same-named-but-different `_normalize()` helpers, YAML quoting-style drift on apostrophe company names, and two defensible-but-arguable industry tags. None block merge.

---

## ✅ Previously Complete & Verified

### UI/UX Overhaul (PR #2 — merged)
Navigation (shared `AppLayout`), agent behavior & persistent preferences (`structured_prefs` now survives reload/new-chat), visual theme (Tailwind v4 tokens), real token streaming. Merged into `main`.

### Job Ranking: Seniority + Company Diversity (merged, pre-dates this session)
Seniority hard-exclusion + company-diversity cap in `select_results.py`/`seniority.py`. This PR's Task 4 extends `select_results.py` further (industry cap) rather than duplicating it.

### Langfuse Observability (PR #1 — merged)
Optional retrospective tracing for agent chat sessions. True no-op when unconfigured.

### All 3 Original Implementation Plans Done
- **Plan 1 — Backend Foundation** (auth, profile, jobs, DB, migrations) ✓
- **Plan 2 — Agent Core & Chat** (LangGraph, `/api/chat` SSE, real Haiku ranking) ✓
- **Plan 3 — Frontend** (React SPA: signup, onboarding, streaming chat, saved jobs) ✓

### API Budget Status
- Started with: $20
- Spent through this session (diagnostics, live company-board validation calls, Haiku throughout): not precisely tracked, expected well under $2 total
- Remaining: rough estimate ~$18-19 / $20

---

## 🔴 Known Gaps (Blockers)

### 1. Deployment Blockers (Required Before Railway)
- [ ] **Dockerfile `$PORT`** — hardcoded 8000, Railway injects `$PORT` env var
- [ ] **No migrations on startup** — prod Postgres empty, every request 500s
- [ ] **`DATABASE_URL` driver mismatch** — Railway gives `postgresql://`, async stack needs `postgresql+asyncpg://`
- [ ] **Never built/tested** — Dockerfile written but not executed locally
- [ ] **Prod env vars missing** — JWT_SECRET, ANTHROPIC_API_KEY, COOKIE_SECURE=true

**Effort**: ~1–1.5 hours (code fixes + local `docker build` + verify).

---

## 🟡 Optional (Pre-Public Launch)

- Rate-limit `/api/chat` (budget protection; per-user daily cap)
- Switch checkpointer from `MemorySaver` (in-memory) to Postgres (persistent, multi-instance); pair with a dedicated jobs DB + cron-worker refresh (would also let seed-list growth stop being throughput-bound on live per-turn fetches — explicitly deferred until then, see design doc)
- Prefilter tie-break/backfill follow-up (see above)
- A dedicated preferences/settings page (explicitly out of scope for the UI/UX overhaul — conversational-only was the deliberate design choice)
- Full preference field taxonomy + hard/soft ambiguity confirmation (see design doc — needs its own scoped brainstorm)

---

## 🔧 How to Continue

### In a Fresh Context
1. Read this file
2. Check memory files in `/Users/briceparrott/.claude/projects/-Users-briceparrott-coding-projects-Lewis/memory/`
3. This PR (job-quality-ranking) is open and ready for your review/merge decision
4. Once merged, natural next work is either the deployment blockers, or the deferred prefilter tie-break/backfill follow-up

### If You Hit Issues
- **Tests fail?** — Run `cd apps/api && uv run pytest -q` (auto-creates test DB).
- **Can't deploy?** — Dockerfile blockers (above) are the likely culprit.
- **Seed list needs re-validation later** (dead tokens accumulate over time) — rerun `cd apps/api && uv run python scripts/validate_seed_companies.py`.

---

## 📊 Current Metrics

| Metric | Value |
|--------|-------|
| **Backend tests** | 91/91 passing, ruff/black clean |
| **Seed companies** | 252 (live-validated, industry-tagged), up from 106 |
| **Fetch concurrency** | 40 (was 15) |
| **API budget remaining** | ~$18-19 / $20 (rough) |
| **This PR** | 5/5 plan tasks + final review fix wave complete, ready for merge |

---

## 📝 Notes

- **Simplicity wins**: All code written for readability, not cleverness. Haiku is default LLM (cost-conscious).
- **Memory persists**: Check `memory/` folder for [[lewis-project]] and [[simplicity-and-cost-preferences]] context.
- **This session's job-quality work**: brainstormed to a paused DRAFT spec pending the UI/UX overhaul; on "merge is in," given full autonomy ("proceed all the way from scoping to implementation without pausing, only pause before merging to main") — resumed the design (updating it with post-merge findings), wrote the plan, ran `superpowers:subagent-driven-development` through all 5 tasks plus a final whole-branch review and fix wave, entirely without interim check-ins, per that instruction.
- **A sandbox boundary was hit**: this worktree-isolated session could not run git operations against the shared main checkout (`/Users/briceparrott/coding/projects/Lewis`) — by design. A stale, superseded draft of the design spec and an uncommitted `status.md` edit from earlier in the session were left behind there, harmlessly (never committed). Safe to `git checkout -- status.md` and delete the stray spec file in the main checkout if you want it clean, or just ignore it.

---

**Last updated**: 2026-08-08 (this session)
**Ready for**: Your review and merge decision on the job-quality-ranking PR.
