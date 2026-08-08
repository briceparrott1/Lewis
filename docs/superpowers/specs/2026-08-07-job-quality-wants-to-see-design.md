# Job Quality: "A Job the User Wants to See" — Design (FINAL for this PR)

**Status: resumed and finalized.** `worktree-ui-ux-overhaul` (PR #2) is
merged into `main` — confirmed via `git log`/`gh pr view 2`
(`state: MERGED`). Brice has given full autonomy to proceed from here
straight through implementation to an open PR with no interim pauses; the
open questions from the paused draft are resolved below by design
judgment call, not further user input. Gate is only before merging to
`main`, which is Brice's to do, not this PR's.

## Post-merge findings that changed the picture

The merged UI/UX overhaul already shipped more than assumed in the
original draft:
- `UserProfile.structured_prefs` persistence is real and working
  (`chat/routes.py`): read at the start of every `/api/chat` call, written
  back after each turn via a separate DB session so persistence failures
  don't break the stream. The original preference-persistence bug from
  the initial debugging pass is resolved — not by this PR.
- `agent/prefs.py`'s extraction schema **already has** a `required`
  (hard/dealbreaker) vs `priorities` (soft, ordered) split — but, same
  limitation as before, both are constrained to the set `['role',
  'location']` only; nothing else can become a hard constraint.
- `agent/clarify.py` (new) generates a conversational clarify reply, but
  **only** for missing role/location(-or-remote) — it has no concept of
  ambiguous hard-vs-soft classification. `route()` in `graph.py` also only
  clarifies once per thread (`clarified_once`), then proceeds to search
  regardless of sufficiency — a reasonable existing UX tradeoff (avoids an
  infinite clarify loop), left as-is.
- Confirmed via code read: `rank_jobs` (`rank.py`) always includes every
  candidate the LLM omitted from its response, defaulted to `score=0,
  reason=""`. `select_results.py` has no score filter — an unscored job
  defaults to `seniority="unknown"`, which is `"unrestricted"` in both
  `filter_by_seniority` and the adjacent-tier cap, so it can reach the
  user's final batch with an empty reason if the eligible pool is thin.
  This is a real, fixable bug, in scope below.
- `prefilter.py`'s role match (`_kw_hit`) is case-insensitive but does
  **no** punctuation/whitespace normalization — `"full stack"` won't
  match `"Full-Stack Engineer"`. Confirmed, in scope below (small fix).
- `seed_companies.yaml` has exactly `{company, source, board_token}` — no
  industry or other metadata field exists yet.

## Scope for this PR

Full field-taxonomy expansion (qualification/desire fields beyond
role/location/seniority) and hard/soft confirmation-on-ambiguity are
**deferred** — those are genuine product decisions (what counts as a
dealbreaker field, how much to interrupt the user to confirm) better
suited to their own scoped brainstorm with Brice's review, not folded
into an autonomous pass. What ships in this PR is the concrete,
well-understood subset directly requested: scaling the company pool
(throughput-constrained only) and fixing the specific algo gaps found in
this and the prior debugging pass. Recorded as follow-up in `status.md`.

**In scope:**
1. Raise `boards.py` fetch concurrency (15 → 40) and add distinct 429
   logging so a rate-limited board is no longer silently indistinguishable
   from "0 matching jobs."
2. Fix the unscored-candidate leak: drop LLM-omitted (`score<=0`,
   unscored) candidates before `select_results`, so they can never reach
   a user's final batch.
3. Normalize `prefilter.py`'s role-keyword matching (strip
   hyphens/collapse whitespace before the substring check, mirroring
   `seniority.py`'s existing `_normalize()` pattern) to reduce false-
   negative exclusions from title-phrasing variance.
4. Add a static `industry` tag per seed company (fixed taxonomy, not a
   live per-turn LLM guess) and extend `select_results.py` with an
   industry diversity cap — generalizing company-only diversity toward
   the broader "vary on axes the user didn't specify" goal. `industry =
   "unknown"` is unrestricted/uncapped, mirroring the existing seniority
   "unknown" handling.
5. Automated discovery + live validation to grow the seed list well
   beyond 106 (target: 300+ validated companies), each tagged with an
   industry from the fixed taxonomy — replacing one-by-one manual
   curation, which doesn't scale.

**Explicitly deferred (not built now, noted in `status.md`):**
- Full qualification/desire field taxonomy from the brainstorm.
- Hard/soft ambiguity confirmation node.
- Extending `required`/`priorities` beyond `role`/`location`.
- Background cache pre-warm (already decided against earlier — waits for
  the future dedicated-DB + cron-worker architecture).
- Dedup resurfacing policy — dedup already exists (`served_keys` in
  `graph.py`'s `search`), the open question was only about whether a
  shown-but-ignored job should ever resurface; leaving current
  permanent-exclusion behavior as-is, undecided question noted for later.

## Relationship to existing work

- `docs/superpowers/specs/2026-08-07-job-ranking-seniority-diversity-design.md`
  (**implemented**: `agent/seniority.py`, `agent/select_results.py`, wired
  into `agent/graph.py`'s `respond`) already ships seniority hard-exclusion
  and a **company** diversity cap (max 2 per company, max 3
  adjacent-seniority-tier). That plan explicitly scoped out preference
  persistence, onboarding fields, and seed-list expansion.
- This work extends that: generalizing "diversity" from company-only to
  arbitrary unspecified axes (industry, company stage, tech stack…), and
  fixing the preference-plumbing gaps that make hard/soft enforcement
  possible in the first place. **Extend `select_results.py`, don't
  duplicate it.**
- Preference *persistence* (profile → agent state surviving page
  reload/session) is being handled separately by another in-progress
  effort — not in scope here. This design assumes prefs data reliably
  reaches the agent and focuses on what happens once it does.

## Problem framing

A job the user "wants to see" clears several distinct layers:

1. **Eligible** — role/seniority/location line up (deterministic, no LLM
   judgment needed).
2. **Aligned** — fits stated preferences (industry, comp floor, remote
   policy, company stage).
3. **Qualified-for** — resume actually supports applying.
4. **New to them** — not a repeat or near-duplicate of something already
   shown/dismissed.
5. **Actually live** — current, real posting.
6. **Legible** — user can tell why it's here at a glance.
7. **Varied, on axes they didn't specify** — per batch, not across
   sessions. If a user asks for "full-stack senior in SF, hybrid," every
   result must fit that, but industry/company-size/stack (unspecified)
   should spread rather than cluster. Confirmed scope: **per-batch**
   variation, not session-to-session.

## Field schema

Two distinct categories — answer different questions, extracted
separately, both nullable (not every field fills):

**From resume → qualification fields ("what they could do"):**
`seniority_level`, `years_experience`, `years_experience_by_domain`,
`skills`/`tech_stack`, `roles_held`, `management_experience`,
`education_level`, `education_field`, `certifications`,
`industries_worked_in`, `company_sizes_worked_at`, `domain_expertise`,
`project_types` (0-to-1 vs scale, B2B vs B2C), `current_location`,
`remote_experience`, `career_trajectory` (IC vs management track).
`employment_gaps` / `work_authorization`: extract only if there's a clear
user-facing use (e.g. surfacing visa-sponsoring companies), never as a
silent penalty.

**From prefs text → desire fields ("what they want"):**
`target_roles`, `target_seniority`, `target_locations`, `work_policy`,
`comp_floor`, `equity_vs_cash_preference`, `industries_wanted`/
`industries_excluded`, `company_stage`, `company_size_preference`,
`team_size_preference`, `mission_alignment` (low-confidence, may cut),
`benefits_priorities`, `role_focus_desired`, `timeline`/`urgency`,
`deal_breakers` (free-form overflow — must actually be enforced
downstream, unlike today's unread `extra` field).

Resume and prefs fields can agree or diverge on the same topic (e.g.
resume shows fintech background, prefs excludes fintech) — not a
conflict, two different signals for two different checks.

## Minimum-to-search gate + clarify loop

Blocks first search:
- At least one `target_role` — no reasonable default.
- At least one `target_location` OR `work_policy == remote` — no
  reasonable default.
- Resume already gates chat access upstream; qualification fields assumed
  available by the time this runs.

Everything else defaults from resume where sane (e.g. `target_seniority`
← resume's `seniority_level` if unstated) rather than blocking.

## Hard/soft preference confirmation

- Hard vs soft must come from the user, not be silently inferred — Lewis
  promises to "very strongly obey" hard preferences.
- Extraction assigns a *provisional* label from literal language ("must
  be hybrid" → hard; "would prefer hybrid" → soft).
- **Only confirm when ambiguous.** Unambiguous language skips
  confirmation entirely (decided explicitly — do not add a confirmation
  step for clear statements).
- Confirmation is a single recap turn covering only the ambiguous fields,
  not one question per field. Sticky once confirmed; only re-triggers on
  new/contradicting statements.

## Proposed graph flow (reviewed interactively, not yet finalized)

```
User message
  → Extract/update fields (resume + prefs text → qual + desire fields)
  → [gate] role + location/remote set?
       no  → Clarify node (ask for missing piece, nudge) → wait for next message
       yes → [gate] any stated pref ambiguous hard/soft?
                yes → Confirm node (recap only the ambiguous ones) → wait for next message
                no  → Search sources (fetch candidates)
                        → Hard filter (role+location gate + confirmed hard prefs + deal-breakers)
                        → Dedup (drop already shown/saved/rejected)
                        → Rank (LLM: qualification fit + soft-preference alignment)
                        → Diversify & select (final batch, spread on unspecified axes) [extends select_results.py]
                        → Narrate & return
```

## Algo review — gaps found, not yet resolved

1. **Rank needs to emit structured axis data, not just a score.**
   Diversify can't spread on industry/company-size/stack unless those are
   attached per candidate. Inferring company industry fresh per search
   via the ranking LLM is wasteful and inconsistent — better as a static
   tag (e.g. add `industry` to `seed_companies.yaml`, or a one-time
   enrichment pass) than a live per-turn LLM guess.
2. **Hard role/location filter is a brittle, unrecoverable gate.**
   `prefilter.py`'s role gate is plain title-substring matching. A false
   negative here is silent and permanent (job never reaches ranking).
   Gets worse as company/title vocabulary grows with seed-list scale.
3. **Diversify needs a defined fallback for a thin survivor pool** —
   degrade gracefully (return what's there) rather than assume a rich
   candidate pool.
4. **Dedup semantics undefined** — does a shown-but-ignored job ever
   resurface (e.g. after prefs change), or excluded forever? Needs a
   decision before implementation.
5. **Existing silent-fallback bug compounds with Diversify.** Jobs the
   ranking LLM fails to score still flow through with `score=0,
   reason=""` (`rank.py`). Diversify must explicitly drop unscored
   candidates first, not rely on low score alone — an unscored job could
   otherwise get picked *for* variety's sake.

## Seed-list scaling — facts gathered, decision deferred

Already shipped (original build, not new): 106 companies
(`seed_companies.yaml`), concurrent fetch via `asyncio.gather` +
semaphore capped at **15**, 5s per-board timeout, in-memory TTL cache
(10 min, per-process, keyed by `(source, board_token)`)
(`agent/sources/boards.py`). Per-board failures isolated (try/except →
`[]`), but **no 429/backoff handling** — a rate-limited board is
indistinguishable from "0 matching jobs."

Scaling constraint is linear batch count at fixed concurrency
(⌈N/15⌉ batches × up to 5s worst case) — a config change (raise
concurrency), not an architecture problem, up to a few hundred
companies. What doesn't scale with config: **curation** — the 106 were
individually live-verified; going further needs automated
discovery+validation (batch-check candidate board tokens, keep only
live ones), not manual curation.

**Explicitly decided NOT to do now:** a background cache pre-warm task
(would fully decouple turn latency from company count, no DB needed).
Deferred to the future dedicated-DB + cron-worker architecture Brice
described. For this pass: raise concurrency, add automated
discovery/validation, leave fetch-live-every-turn as is.

## Resolved decisions for this PR

- **Rank output**: no change to `rank.py`'s output — industry is a
  *static* company-level tag attached at fetch time (`boards.py`/seed
  data), not something Rank needs to infer live. Avoids an extra LLM
  round-trip and keeps classification consistent across users/turns.
- **Diversify axis for this PR**: industry only (fixed taxonomy — see
  Task 4 in the plan), added alongside the existing company/seniority
  caps in `select_results.py`. Other axes (company size, stage, stack)
  deferred — same reasoning as the full field taxonomy: needs its own
  data source and scoping, not bolted on here.
- **Concurrency**: raised to 40 (from 15). At a 300+ company target that
  keeps worst-case batch count (⌈N/40⌉) comparable to today's
  ⌈106/15⌉≈8 batches. `httpx.AsyncClient`'s default connection-pool
  limits (100 max connections) comfortably cover this without a separate
  `httpx.Limits` override.
- **Board-token discovery**: no single authoritative source exists;
  approach is to compile candidate company names from public
  developer-jobs/company lists via web research, derive likely board
  tokens, and validate every candidate live against the same two
  endpoints the original 106 were checked against — keep only entries
  that return HTTP 200 with a non-empty job list. Same validation bar as
  the existing file's own header comment describes.

## Remaining open questions (genuinely deferred, not this PR)

- Full qualification/desire field taxonomy and hard/soft ambiguity
  confirmation — needs its own brainstorm/spec.
- Dedup resurfacing policy (does a shown-but-ignored job ever come back?).
- Additional diversify axes beyond industry (company size, stage, stack).
