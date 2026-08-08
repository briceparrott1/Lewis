# Lewis — Project Status

**As of 2026-08-08** | Repo: https://github.com/briceparrott1/Lewis | Branch: `main`

## 🔵 Open PR — Needs Your Merge Decision

**UI/UX overhaul** — branch `worktree-ui-ux-overhaul`, worktree at `.claude/worktrees/ui-ux-overhaul`. PR not yet opened; see "How to Continue" below (opening it is the next action in this session).

Four phases, each independently shippable, built via brainstorm → spec (`docs/superpowers/specs/2026-08-07-ui-ux-overhaul-design.md`) → plan (`docs/superpowers/plans/2026-08-07-ui-ux-overhaul.md`, 15 tasks) → subagent-driven implementation → per-task reviews → final whole-branch review (opus) → one fix wave → clean:

1. **Navigation** — shared `AppLayout` header (Chat/Saved/Profile nav + logout), wired into routing via a layout route. Previously there was no way to navigate between authenticated pages at all.
2. **Agent behavior & persistent preferences** — `UserProfile.structured_prefs` (a DB column that existed but was never wired up) is now read into the LangGraph agent every turn and written back after, so preferences survive "New chat," reload, and restart. The hardcoded clarify text is replaced by an LLM-generated reply that acknowledges what the user actually said (tested live: "hey there, how's it going?" → "Hey! Doing great, thanks for asking! So I see you're looking for senior-level Forward Deployed Engineer..."). Chat opens with a template-rendered (no LLM call) greeting, personalized with name and — for returning users — a summary of prior preferences.
3. **Visual theme** — Tailwind v4 `@theme` design tokens (chat-first minimal: indigo accent, soft shadows, rounded bubbles) applied consistently across every page.
4. **Real token streaming** — narrative and clarify replies now stream token-by-token over SSE (`narrative_delta`/`clarify_delta` events) instead of appearing all at once, with the existing terminal events serving as the authoritative reconciliation point if a delta drops in transit.

**Verification:** 82/82 backend tests, 37/37 frontend tests, ruff/black/typecheck/build all clean. Final whole-branch review caught two Important integration-level bugs (invisible to any single task's review) that are now fixed: an empty-but-successful LLM stream could leave a blank chat bubble with no fallback text; the "New chat" greeting read a stale cached profile and never reflected preferences learned earlier in the same session. Both fixed and re-verified. Manually walked through the live app in-browser end to end (signup → onboarding → chat greeting → smalltalk ack → real Greenhouse/Ashby search + Haiku ranking + streaming narrative → New chat showing the persisted-preference greeting → Saved page) — everything works as designed.

A handful of Minor findings were deliberately deferred rather than fixed (see `.superpowers/sdd/2026-08-07-ui-ux-overhaul/progress.md` in that worktree for the full ledger before it's deleted): a couple of no-op lint-suppression comments, missing `aria-label`/`<main>` landmark on the header, a narrow concurrent-first-chat race on profile-row creation, and two test-coverage gaps (delta-accumulation isn't independently tested; the clarify_delta path doesn't hide the spinner as fast as narrative_delta does). None block merge.

---

## ✅ Previously Complete & Verified

### Langfuse Observability (PR #1 — merged)
Optional retrospective tracing for agent chat sessions (node sequence + per-call prompt/completion/token detail). True no-op when unconfigured; fails open if Langfuse itself errors. Merged into `main`.

### All 3 Original Implementation Plans Done
- **Plan 1 — Backend Foundation** (auth, profile, jobs, DB, migrations) ✓
- **Plan 2 — Agent Core & Chat** (LangGraph, `/api/chat` SSE, real Haiku ranking) ✓
- **Plan 3 — Frontend** (React SPA: signup, onboarding, streaming chat, saved jobs) ✓

### API Budget Status
- Started with: $20
- Spent through this session (builds, diagnostics, live smoke tests, the UI/UX overhaul's manual browser walkthrough): still well under $1 total (Haiku throughout)
- Remaining: ~$19 (rough — not precisely tracked this session)

---

## 🔴 Known Gaps (Blockers) — unrelated to the UI/UX overhaul, still open

### 1. Seed List Too Small (High Priority — UX Impact)
**Problem**: Seed has only a handful of companies (GitLab, Ramp, Cloudflare, Coinbase seen in this session's live test). Specific/niche queries outside tech-company hiring return 0 results.

**Fix**: Expand to 100+ tech companies across industries, validate against live Greenhouse/Ashby APIs.

**Effort**: ~1–2 hours (research + batch-validate with Haiku).

### 2. Deployment Blockers (Required Before Railway)
- [ ] **Dockerfile `$PORT`** — hardcoded 8000, Railway injects `$PORT` env var
- [ ] **No migrations on startup** — prod Postgres empty, every request 500s
- [ ] **`DATABASE_URL` driver mismatch** — Railway gives `postgresql://`, async stack needs `postgresql+asyncpg://`
- [ ] **Never built/tested** — Dockerfile written but not executed locally
- [ ] **Prod env vars missing** — JWT_SECRET, ANTHROPIC_API_KEY, COOKIE_SECURE=true

**Effort**: ~1–1.5 hours (code fixes + local `docker build` + verify).

---

## 🟡 Optional (Pre-Public Launch)

- Rate-limit `/api/chat` (budget protection; per-user daily cap)
- Switch checkpointer from `MemorySaver` (in-memory) to Postgres (persistent, multi-instance) — note: chat-turn `clarified_once` state is still in-memory-only even after this session's persistence work; only `structured_prefs` was made durable, by design (see spec)
- Seed-list auto-fetch from Greenhouse/Ashby (vs. manual curation)
- A dedicated preferences/settings page (explicitly out of scope for the UI/UX overhaul — conversational-only was the deliberate design choice)

---

## 🔧 How to Continue

### In a Fresh Context
1. Read this file
2. Check memory files in `/Users/briceparrott/.claude/projects/-Users-briceparrott-coding-projects-Lewis/memory/`
3. If the UI/UX overhaul PR isn't open yet: `cd` into `.claude/worktrees/ui-ux-overhaul`, push the branch, and open a PR against `main` (work is complete and verified — this is just the mechanical push+PR step)
4. Once that's merged, next natural work is **Expand Seed List** — self-contained, directly fixes the 0-results UX gap

### If You Hit Issues
- **Tests fail?** — Run `cd apps/api && uv run pytest -q` (auto-creates test DB) and `cd apps/web && pnpm test`.
- **Can't deploy?** — Dockerfile blockers (above) are the likely culprit.

---

## 📊 Current Metrics

| Metric | Value |
|--------|-------|
| **Backend tests** | 82/82 passing, ruff/black clean |
| **Frontend tests** | 37/37 passing, typecheck clean, build succeeds |
| **API budget remaining** | ~$19 / $20 |
| **UI/UX overhaul** | 15/15 plan tasks complete, final review clean, ready for PR |

---

## 📝 Notes

- **Simplicity wins**: All code written for readability, not cleverness. Haiku is default LLM (cost-conscious).
- **Memory persists**: Check `memory/` folder for [[lewis-project]] and [[simplicity-and-cost-preferences]] context.
- **This session's UI/UX overhaul** used `superpowers:subagent-driven-development` throughout: a fresh implementer subagent per task, an independent reviewer per task, and a final opus-model whole-branch review before considering the branch done. The plan document originally numbered tasks "Task 1, Task 2, ..." restarting within each phase, which broke the SDD tooling's brief-extraction script (it matches on heading number only, with no notion of phase boundaries) — renumbered globally 1–15 early in execution, before any task was dispatched.

---

**Last updated**: 2026-08-08
**Ready for**: Pushing the `worktree-ui-ux-overhaul` branch and opening a PR (work complete, gated only on your merge decision per your standing preference).
