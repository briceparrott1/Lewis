# Job Ranking: Seniority Enforcement + Company Diversity

## Problem

Users report two recurring quality issues with recommended jobs:

1. New-grad roles get recommended to senior candidates (and vice versa).
2. Recommendation sets are dominated by a single company (observed: 6 of 7
   results from one company).

Investigation traced both to gaps between the original implementation plan
(`docs/superpowers/plans/2026-08-06-agent-core-chat.md`) and what actually
shipped:

- `StructuredPrefs.seniority` (`agent/state.py`) is parsed from the
  conversation (`agent/prefs.py`) and stored in agent state, but
  `agent/prefilter.py` never reads it — not in the hard `required` filter,
  not in soft scoring. It only reaches the LLM ranker
  (`agent/rank.py`) as inert JSON context with no enforcement.
- There is no company-diversity or per-company cap logic anywhere in the
  pipeline (`prefilter.py`, `rank.py`, or the `respond` node in
  `graph.py`). Jobs are deduped only by URL and the final top-N is a pure
  score sort, so a company with many open reqs can dominate the results.
- The job pool itself (106 seed companies, live-fetched via
  Greenhouse/Ashby, prefiltered to a capped 50 candidates before ranking)
  is not the bottleneck — the gap is in enforcement after the candidate
  pool is built, not in pool size.

## Goals

- Never show a job whose seniority is clearly below or clearly above (2+
  ladder tiers) the user's stated seniority.
- Allow controlled flexibility: a job one ladder tier *above* the user's
  level may appear, but only up to a cap, so a new-grad candidate can see
  some mid-level openings without the result set skewing senior.
- Never let one company dominate a result set.

## Non-goals (out of scope for this change)

- Fixing preference persistence across conversations (`structured_prefs`
  fetched-but-unused bug in `chat/routes.py`) — tracked separately.
- Adding explicit preference fields to onboarding (years of experience,
  company size, etc.).
- Changing how the candidate pool is sourced or expanding beyond the
  106-company seed list.

## Design

### Seniority ladder

```
intern < new_grad < mid < senior < staff
```

### Classification

Extend the existing single LLM ranking call in `agent/rank.py`
(`_SCHEMA`, currently `score` + `reason` per job) to also return a
per-job `seniority` classification, one of:
`intern | new_grad | mid | senior | staff | unknown`.

The LLM already receives each job's `title` and `description[:800]` in
that same call — classification piggybacks on it with no additional LLM
round-trip and no added cost.

### Seniority rules

Given the user's `prefs["seniority"]` (when set) and a job's classified
seniority:

| Relationship to user's tier | Outcome |
|---|---|
| Exact match | Always eligible, uncapped |
| One tier above | Eligible, capped at 3 of the 7 final results |
| One tier below, or 2+ tiers in either direction | Hard-excluded |
| `unknown` | Always eligible, uncapped, not counted toward the adjacent-tier cap |
| `prefs["seniority"]` not set | No seniority filtering applied at all |

This filtering is unconditional whenever `prefs.seniority` is set — it
does not route through the existing `required[]` list mechanism (which
today only supports `role`/`location`), since the goal is "always
enforce when known," not "only when the user explicitly flags it as
required."

Hard-excluded jobs (one tier below, or 2+ tiers away) are dropped from
the candidate list entirely, before final selection. Exact-match,
adjacent-tier, and unknown jobs all remain eligible for final selection,
subject to the caps below.

### Company diversity rule

At most 2 jobs from the same company in the final result set.

### Combined final-selection algorithm

Both caps (company diversity and adjacent-tier seniority) interact, so
they're enforced in a single pass rather than as separate filtering
steps. After ranking, classification, and hard seniority exclusion, walk
the score-sorted candidate list and greedily build the result set:

1. Take the next-highest-scored remaining candidate.
2. Skip it (move to the next candidate) if including it would push its
   company's count in the result set above 2.
3. Skip it if it's classified as adjacent-tier (one above the user's
   level) and the adjacent-tier count in the result set has already hit
   3.
4. Otherwise include it.
5. Repeat until 7 slots are filled or candidates are exhausted.

This lives as a new step in `graph.py`, after `rank_jobs()` and the new
seniority hard-exclusion step, replacing the current "sort by score and
slice" logic in `respond`.

### Config change

`max_results` in `agent/config.py`: 6 → 7.

## Error handling

If the LLM omits or emits an invalid `seniority` value for a job (schema
validation), it falls back to `"unknown"` — fails open, consistent with
the rest of the ranking pipeline, rather than breaking ranking or
excluding the job.

## Testing

- `test_rank.py`: LLM mocked (per existing project convention), assert
  the extended schema's `seniority` field is parsed and defaults to
  `"unknown"` on missing/invalid values.
- New test(s) for the seniority hard-exclusion step: given ranked jobs
  spanning all five tiers plus `unknown`, and a user pref of e.g.
  `"mid"`, assert `intern`/`senior`/`staff` are excluded, `new_grad`
  passes through only up to the adjacent-tier cap, `mid` and `unknown`
  are unrestricted.
- New test(s) for the combined final-selection algorithm: given a
  candidate set where one company would otherwise dominate and/or
  adjacent-tier jobs would otherwise exceed 3, assert both caps hold and
  the highest-scored eligible candidates are still preferred.

## Known risk (not addressed by this design)

This design's real-world effectiveness depends on the LLM reliably
classifying job seniority rather than defaulting to `"unknown"` too
often (e.g. generic titles like "Software Engineer" with no level cue).
Unknowns are uncapped by design, so a high unknown rate would blunt the
seniority fix's impact. Not addressed now; if it becomes a problem in
practice, a cap on unknowns is a small follow-up, not a rework.
