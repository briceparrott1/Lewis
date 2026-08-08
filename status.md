# Lewis — Project Status

**As of 2026-08-07** | Repo: https://github.com/briceparrott1/Lewis | Branch: `main`

## 🔵 Open PR — Needs Your Merge Decision

**[PR #1](https://github.com/briceparrott1/Lewis/pull/1) — Optional Langfuse tracing for agent chat sessions**, branch `worktree-langfuse-observability`, worktree at `.claude/worktrees/langfuse-observability`.

Lets a developer retrospectively inspect a chat session (node sequence + per-call prompt/completion/token detail) via Langfuse. True no-op when unconfigured; fails open if Langfuse itself errors once configured. Built via brainstorm → spec (`docs/superpowers/specs/2026-08-07-langfuse-observability-design.md`) → plan (`docs/superpowers/plans/2026-08-07-langfuse-observability.md`) → subagent-driven implementation → final whole-branch review, which caught and fixed two real SDK-version bugs (implementation targeted Langfuse v3 API; installed version was v4.14.3).

73/73 backend tests passing, ruff/black clean. Deliberately gated here: merging to `main` and any manual smoke test with real Langfuse Cloud keys are left for you.

**To use it:** create a Langfuse Cloud account, set `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` in `.env` (already scaffolded in `.env.example`) — you mentioned you'd already added these to the main checkout's `.env`, which doesn't carry into the PR's worktree automatically.

---

## ✅ Complete & Verified

### All 3 Implementation Plans Done
- **Plan 1 — Backend Foundation** (auth, profile, jobs, DB, migrations) ✓
- **Plan 2 — Agent Core & Chat** (LangGraph, `/api/chat` SSE, real Haiku ranking) ✓
- **Plan 3 — Frontend** (React SPA: signup, onboarding, streaming chat, saved jobs) ✓

### End-to-End Product Works
- **User flow tested in browser**: signup → auth guard → onboarding (upload resume) → streaming chat (real Greenhouse/Ashby boards + Haiku ranking) → save jobs → saved view
- **34 backend tests + 7 web tests passing** (all green)
- **Lint clean** (ruff + black)
- **Auto-creates test DB** — no manual `CREATE DATABASE` needed

### Recent Fixes (this session)
1. **Onboarding upload UX** — styled dashed dropzone replaces invisible native control (`89c1add`)
2. **Test DB auto-creation** — conftest now creates `lewis_test` if missing (`065c77c`)
3. **Post-auth redirect race** — signup/login now await `me` refetch before routing (`1bcbff3`)

### API Budget Status
- Started with: $20
- Spent on builds, diagnostics, live smoke tests: **~$0.20**
- Remaining: **~$19.80**

---

## 🔴 Known Gaps (Blockers)

### 1. Seed List Too Small (High Priority — UX Impact)
**Problem**: Seed has only GitLab (devtools) + Ramp (fintech). When user asked for "defense industry sales engineer roles in DC/New York," returned 0 results (correct, but unusable).

**Data**: 312 jobs across seed, 0 sales engineers, 0 defense companies.

**Impact**: Product feels broken to real users; every specific query outside tech startup hiring fails.

**Fix**: Expand to 100+ tech companies across industries, validate against live Greenhouse/Ashby APIs.

**Effort**: ~1–2 hours (research + batch-validate with Haiku).

### 2. Deployment Blockers (Required Before Railway)
- [ ] **Dockerfile `$PORT`** — hardcoded 8000, Railway injects `$PORT` env var
- [ ] **No migrations on startup** — prod Postgres empty, every request 500s
- [ ] **`DATABASE_URL` driver mismatch** — Railway gives `postgresql://`, async stack needs `postgresql+asyncpg://`
- [ ] **Never built/tested** — Dockerfile written but not executed locally
- [ ] **Prod env vars missing** — JWT_SECRET, ANTHROPIC_API_KEY, COOKIE_SECURE=true

**Effort**: ~1–1.5 hours (code fixes + local `docker build` + verify).

### 3. Empty-State UX
When no results: shows "Found 0 roles" without context. Should explain *why* ("none at the companies we track — try broadening your criteria").

**Effort**: ~15 min (one-line message update).

---

## 🟡 Optional (Pre-Public Launch)

- Rate-limit `/api/chat` (budget protection; per-user daily cap)
- Switch checkpointer from `MemorySaver` (in-memory) to Postgres (persistent, multi-instance)
- Seed-list auto-fetch from Greenhouse/Ashby (vs. manual curation)
- Better error messages for upload failures

---

## 📋 Immediate Next Steps

### 1. Expand Seed List (Start Here)
**Rationale**: Direct fix for the 0-results issue; unblocks UX feedback.

**Approach**:
- Research 100 tech companies with public Greenhouse/Ashby boards
- Batch-validate tokens with Haiku (cheap: ~$0.50 for 100 API checks)
- Update `apps/api/lewis_api/agent/sources/seed_companies.yaml`
- Verify 5+ jobs per company before adding (no dead tokens)
- Commit + push

**Owner**: Next context / fresh session

### 2. Fix Deployment Blockers
**Rationale**: Unlocks Railway setup (only 15–30 min of *your* clicks after these are done).

**Approach**:
- Fix Dockerfile: `$PORT` env var + migrations-on-start
- Transform `DATABASE_URL` (strip `+asyncpg` for Postgres connection)
- Local `docker build` + run image to verify
- Commit + test against real Docker

**Owner**: Next context / fresh session

### 3. Deploy to Railway
**Rationale**: Ship the product.

**Your clicks only**:
- Create Railway project
- Add Postgres plugin
- Connect GitHub repo
- Paste env vars (JWT_SECRET, ANTHROPIC_API_KEY, COOKIE_SECURE=true)
- Watch first deploy

---

## 🔧 How to Continue

### In a Fresh Context
1. Read this file
2. Check memory files in `/Users/briceparrott/.claude/projects/-Users-briceparrott-coding-projects-Lewis/memory/`
3. Start with **Expand Seed List** task — it's self-contained and directly fixes the UX gap

### If You Hit Issues
- **Can't deploy?** — Dockerfile blockers are the likely culprit. Run `docker build -t lewis .` locally to see errors.
- **Seed validation fails?** — Some tokens may be invalid. The validation script will show which; skip dead ones.
- **Tests fail after changes?** — Run `cd apps/api && uv run pytest -q` (auto-creates test DB now).

---

## 📊 Current Metrics

| Metric | Value |
|--------|-------|
| **Tests passing** | 34 backend + 7 web = **41 total** |
| **Lint status** | ✓ Clean (ruff + black) |
| **API budget remaining** | ~$19.80 / $20 |
| **Seed companies** | 2 (GitLab, Ramp) |
| **Seed jobs total** | 312 |
| **Code commits (this session)** | 8 (Plans 1–3 + fixes) |
| **Lines of code** | ~3000 (Python backend + React web) |

---

## 🎯 Success Criteria (Before Shipping)

- [ ] Seed list: 100 companies, all validated
- [ ] Deployment blockers fixed + Docker image builds locally
- [ ] Empty-state message explains why 0 results
- [ ] Deployed to Railway (public URL works)
- [ ] Real user can sign up → upload resume → get meaningful results

---

## 📝 Notes

- **Simplicity wins**: All code written for readability, not cleverness. Haiku is default LLM (cost-conscious).
- **No clever hacks**: Auto-test-DB creation, plain substring matching (not initials), await refetch before redirect — all dumb-simple solutions.
- **Memory persists**: Check `memory/` folder for [[lewis-project]] and [[simplicity-and-cost-preferences]] context.
- **Deferred cosmetics**: "Ranking 312 matches" status line shows pre-filter count (low priority).

---

**Last updated**: 2026-08-07 01:53 UTC
**Ready for**: Seed-list expansion or deployment work, whichever comes next.
