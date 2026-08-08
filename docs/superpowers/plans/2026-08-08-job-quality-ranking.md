# Job Quality: Ranking Fixes + Seed-List Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the concrete algo gaps and seed-scale bottleneck identified in
`docs/superpowers/specs/2026-08-07-job-quality-wants-to-see-design.md` —
raise fetch throughput, stop unscored candidates from reaching users, make
the required role-keyword filter resilient to title-phrasing variance, and
generalize the existing company-diversity cap to also spread on industry,
backed by a much larger validated seed list.

**Architecture:** No new graph nodes. All changes are inside existing
modules: `agent/sources/boards.py` (concurrency + failure visibility),
`agent/rank.py` (drop LLM-omitted candidates instead of defaulting them
in), `agent/prefilter.py` (normalize role-keyword matching),
`agent/sources/seed.py` + `agent/state.py` + `agent/select_results.py`
(new `industry` field + cap), and a one-time data-generation pass that
rewrites `agent/sources/seed_companies.yaml` with a much larger,
live-validated, industry-tagged company list.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, httpx, pytest +
pytest-asyncio, uv.

## Global Constraints

- Python style: PEP 8, Black-formatted (88 cols), Ruff-clean
  (`ruff check .`), type hints on public APIs (per project/global
  CLAUDE.md).
- Tests use the existing `FakeLLM`/`monkeypatch` mocking patterns already
  present in `tests/agent/test_rank.py`, `tests/agent/test_boards.py`,
  `tests/agent/test_select_results.py` — never call the real Anthropic
  API or real Greenhouse/Ashby APIs in the pytest suite.
- Fixed industry taxonomy (used by Task 4 and Task 5):
  `fintech, healthtech, devtools, cybersecurity, ecommerce,
  enterprise_saas, consumer, ai_ml, biotech, media_entertainment,
  real_estate, logistics_supply_chain, gaming, edtech,
  hardware_robotics, climate_energy, unknown`.
- `industry == "unknown"` is always unrestricted/uncapped, mirroring the
  existing seniority "unknown" handling in `seniority.py` — never treat
  missing industry data as a penalty.
- No fabricated seed data: every entry in the final
  `seed_companies.yaml` must be a real company independently live-checked
  against its Greenhouse/Ashby board endpoint (HTTP 200 + non-empty job
  list) before being added — same bar the existing 106 were held to (see
  the file's own header comment).

---

### Task 1: Raise fetch concurrency, make rate-limiting visible

**Files:**
- Modify: `apps/api/lewis_api/agent/sources/boards.py`
- Test: `apps/api/tests/agent/test_boards.py`

**Interfaces:**
- `fetch_all_boards(entries, client, *, concurrency: int = 40, timeout: float = 5.0)` — signature unchanged except the `concurrency` default (was 15).

- [ ] **Step 1: Write the failing tests**

Add to `apps/api/tests/agent/test_boards.py`:

```python
import logging

import httpx


def test_default_concurrency_is_40():
    import inspect

    sig = inspect.signature(boards.fetch_all_boards)
    assert sig.parameters["concurrency"].default == 40


@pytest.mark.asyncio
async def test_rate_limited_board_logs_warning_and_fails_open(monkeypatch, caplog):
    async def fake_gh(token, client):
        request = httpx.Request("GET", "https://x")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError("rate limited", request=request, response=response)

    async def fake_ashby(org, client):
        return [Job(source="ashby", url=f"https://x/{org}/1", title="A")]

    monkeypatch.setattr(boards, "fetch_greenhouse", fake_gh)
    monkeypatch.setattr(boards, "fetch_ashby", fake_ashby)
    boards._CACHE.clear()

    entries = [
        boards.SeedEntry("GitLab", "greenhouse", "gitlab"),
        boards.SeedEntry("Ramp", "ashby", "ramp"),
    ]
    with caplog.at_level(logging.WARNING):
        jobs = await boards.fetch_all_boards(entries, client=None)
    assert len(jobs) == 1  # 429 board skipped, ashby kept
    assert any(
        "429" in r.message or "rate limit" in r.message.lower() for r in caplog.records
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/agent/test_boards.py -v`
Expected: `test_default_concurrency_is_40` FAILs (default is still 15). `test_rate_limited_board_logs_warning_and_fails_open` FAILs (no warning logged today — generic `except Exception` swallows it silently).

- [ ] **Step 3: Implement**

In `apps/api/lewis_api/agent/sources/boards.py`:
- Add `import logging` and `logger = logging.getLogger(__name__)` near the top.
- Change `fetch_all_boards`'s `concurrency: int = 15` to `concurrency: int = 40`.
- Replace the `guarded()` body:

```python
    async def guarded(entry: SeedEntry) -> list[Job]:
        async with sem:
            try:
                return await _fetch_one(entry, client, timeout)
            except httpx.HTTPStatusError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    logger.warning(
                        "rate limited fetching %s/%s", entry.source, entry.board_token
                    )
                else:
                    logger.info(
                        "board fetch failed for %s/%s: %s",
                        entry.source,
                        entry.board_token,
                        exc,
                    )
                return []
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    "board fetch failed for %s/%s: %s",
                    entry.source,
                    entry.board_token,
                    exc,
                )
                return []  # partial-failure tolerant: skip this board
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_boards.py -v`
Expected: PASS (both new tests and the pre-existing `test_fetch_all_boards_merges_and_tolerates_failure`).

- [ ] **Step 5: Lint and format**

Run: `cd apps/api && uv run ruff check . && uv run black --check .`
Expected: no errors. If Black reports issues, run `uv run black .` and re-check.

- [ ] **Step 6: Commit**

```bash
git add apps/api/lewis_api/agent/sources/boards.py apps/api/tests/agent/test_boards.py
git commit -m "feat: raise fetch concurrency to 40, log rate-limited boards distinctly"
```

---

### Task 2: Stop unscored candidates from silently reaching users

**Files:**
- Modify: `apps/api/lewis_api/agent/rank.py`
- Test: `apps/api/tests/agent/test_rank.py`

**Interfaces:**
- `rank_jobs(candidates, prefs, resume_text, llm) -> list[RankedJob]` — signature unchanged. Behavior change: candidates the LLM's response entirely omits (not present in `rankings` at all) are now dropped from the return value, instead of being defaulted in with `score=0, reason=""`. Candidates present in the response but missing one field (e.g. `seniority`) are unaffected — they still fall back per-field as before.

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/agent/test_rank.py`:

```python
@pytest.mark.asyncio
async def test_rank_drops_candidates_omitted_entirely_from_llm_response():
    cands = [
        {"external_id": "1", "title": "FDE", "url": "u1", "description": "x"},
        {"external_id": "2", "title": "SE", "url": "u2", "description": "y"},
    ]
    llm = FakeLLM(
        {
            "rankings": [
                {"external_id": "1", "score": 60, "reason": "ok", "seniority": "mid"},
                # "2" entirely absent from the LLM's response
            ]
        }
    )
    out = await rank_jobs(cands, {}, "resume", llm)
    assert [j["external_id"] for j in out] == ["1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/agent/test_rank.py::test_rank_drops_candidates_omitted_entirely_from_llm_response -v`
Expected: FAIL — today candidate "2" is still returned with `score=0, reason=""`.

- [ ] **Step 3: Implement**

In `apps/api/lewis_api/agent/rank.py`, replace the loop body of `rank_jobs`:

```python
    by_id = {r["external_id"]: r for r in result.get("rankings", [])}
    ranked: list[RankedJob] = []
    for c in candidates:
        ext_id = c.get("external_id")
        if ext_id not in by_id:
            continue  # LLM never addressed this candidate — don't show it
        r = by_id[ext_id]
        seniority = r.get("seniority", "unknown")
        if seniority not in _VALID_SENIORITY:
            seniority = "unknown"
        ranked.append(
            RankedJob(
                **c,
                score=int(r.get("score", 0)),
                reason=r.get("reason", ""),
                seniority=seniority,
            )
        )
    ranked.sort(key=lambda j: j.get("score", 0), reverse=True)
    return ranked
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_rank.py -v`
Expected: PASS (new test, plus both pre-existing tests — confirm
`test_rank_includes_seniority_and_falls_back_to_unknown` still passes,
since all 3 of its candidates remain present in the fake `rankings`
response and only differ by a missing/invalid `seniority` field, not
absence from the response).

- [ ] **Step 5: Lint and format**

Run: `cd apps/api && uv run ruff check . && uv run black --check .`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add apps/api/lewis_api/agent/rank.py apps/api/tests/agent/test_rank.py
git commit -m "fix: drop candidates the ranking LLM omitted, instead of defaulting them into results"
```

---

### Task 3: Normalize role-keyword matching in the hard filter

**Files:**
- Modify: `apps/api/lewis_api/agent/prefilter.py`
- Test: `apps/api/tests/agent/test_prefilter.py`

**Interfaces:**
- `_kw_hit` gains hyphen/underscore/whitespace-insensitive matching. `prefilter()`'s public signature is unchanged.

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/agent/test_prefilter.py` (check the existing file first for its exact `Job`-construction helper/import style and match it):

```python
def test_role_keyword_matches_across_hyphen_and_case_variance():
    job_hyphenated = {"title": "Full-Stack Engineer", "location": ""}
    job_spaced = {"title": "Full Stack Engineer", "location": ""}
    assert prefilter([job_hyphenated], {"role_keywords": ["full stack"], "required": ["role"]})
    assert prefilter([job_spaced], {"role_keywords": ["full-stack"], "required": ["role"]})
```

(Adjust to match whatever minimal-`Job`-dict / assertion style the existing tests in that file already use — e.g. if they assert on returned list length or job identity rather than truthiness, follow that convention instead.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/agent/test_prefilter.py -v`
Expected: FAIL — today's plain substring match on `.lower()` alone doesn't bridge the hyphen/space difference in either direction.

- [ ] **Step 3: Implement**

In `apps/api/lewis_api/agent/prefilter.py`, add a normalizer and use it in `_kw_hit`:

```python
def _normalize(text: str) -> str:
    """Collapse hyphen/underscore/whitespace variance so role-keyword
    matching isn't tripped up by title phrasing (e.g. "Full-Stack" vs
    "full stack")."""
    return " ".join(text.strip().lower().replace("-", " ").replace("_", " ").split())


def _kw_hit(text: str, keywords: list[str]) -> bool:
    low = _normalize(text)
    return any(_normalize(k) in low for k in keywords)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_prefilter.py -v`
Expected: PASS (new test plus all pre-existing prefilter tests).

- [ ] **Step 5: Lint and format**

Run: `cd apps/api && uv run ruff check . && uv run black --check .`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add apps/api/lewis_api/agent/prefilter.py apps/api/tests/agent/test_prefilter.py
git commit -m "fix: normalize hyphen/whitespace variance in role-keyword matching"
```

---

### Task 4: Add a static `industry` field and extend the diversity cap

**Files:**
- Modify: `apps/api/lewis_api/agent/sources/seed.py`, `apps/api/lewis_api/agent/state.py`, `apps/api/lewis_api/agent/sources/boards.py`, `apps/api/lewis_api/agent/select_results.py`
- Test: `apps/api/tests/agent/test_boards.py`, `apps/api/tests/agent/test_select_results.py`

**Interfaces:**
- `SeedEntry` gains `industry: str = "unknown"` (default keeps `load_seed()` backward-compatible with any not-yet-tagged rows).
- `Job`/`RankedJob` gain `industry: str`.
- `select_results()` signature unchanged; behavior gains an industry cap alongside the existing company/seniority caps.

- [ ] **Step 1: Write the failing tests**

Add to `apps/api/tests/agent/test_boards.py` (extends the existing fake-fetcher pattern):

```python
@pytest.mark.asyncio
async def test_fetch_attaches_entry_company_and_industry(monkeypatch):
    async def fake_gh(token, client):
        # fetcher returns the raw token as company, same as real fetch_greenhouse today
        return [Job(source="greenhouse", company=token, url=f"https://x/{token}/1", title="A")]

    monkeypatch.setattr(boards, "fetch_greenhouse", fake_gh)
    boards._CACHE.clear()

    entry = boards.SeedEntry("GitLab", "greenhouse", "gitlab", industry="devtools")
    jobs = await boards.fetch_all_boards([entry], client=None)
    assert jobs[0]["company"] == "GitLab"  # overlaid with the display name, not the raw token
    assert jobs[0]["industry"] == "devtools"
```

Add to `apps/api/tests/agent/test_select_results.py`:

```python
def test_industry_cap_enforced():
    ranked = [
        _job("1", "A", 99, industry="fintech"),
        _job("2", "B", 98, industry="fintech"),
        _job("3", "C", 97, industry="fintech"),
        _job("4", "D", 96, industry="fintech"),  # 4th fintech -> skipped
        _job("5", "E", 50, industry="devtools"),
    ]
    out = select_results(ranked, {}, max_results=5)
    assert [j["external_id"] for j in out] == ["1", "2", "3", "5"]


def test_unknown_industry_is_unrestricted():
    ranked = [_job(str(i), f"Co{i}", 100 - i, industry="unknown") for i in range(5)]
    out = select_results(ranked, {}, max_results=5)
    assert len(out) == 5  # no industry cap applied to "unknown"
```

Update the `_job()` test helper in `test_select_results.py` to accept an `industry="unknown"` default kwarg, matching the existing `seniority="unknown"` pattern already there.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/agent/test_boards.py tests/agent/test_select_results.py -v`
Expected: FAILs — `SeedEntry` doesn't accept `industry` yet, `Job` has no `industry` key, `select_results` has no industry cap.

- [ ] **Step 3: Implement**

In `apps/api/lewis_api/agent/sources/seed.py`, add the field:

```python
@dataclass(frozen=True)
class SeedEntry:
    company: str
    source: str
    board_token: str
    industry: str = "unknown"
```

In `apps/api/lewis_api/agent/state.py`, add `industry: str` to both `Job` and (inherited automatically) `RankedJob`:

```python
class Job(TypedDict, total=False):
    ...
    description: str
    industry: str
```

In `apps/api/lewis_api/agent/sources/boards.py`'s `_fetch_one`, overlay the entry's display name and industry onto every fetched job (also fixes an existing inconsistency where `company` was left as the raw board token from the fetchers):

```python
    fetcher = fetch_greenhouse if entry.source == "greenhouse" else fetch_ashby
    jobs = await asyncio.wait_for(fetcher(entry.board_token, client), timeout)
    for job in jobs:
        job["company"] = entry.company
        job["industry"] = entry.industry
    _CACHE[key] = (time.monotonic(), jobs)
    return jobs
```

In `apps/api/lewis_api/agent/select_results.py`:

```python
COMPANY_CAP = 2
ADJACENT_TIER_CAP = 3
INDUSTRY_CAP = 3


def select_results(
    ranked: list[RankedJob],
    prefs: StructuredPrefs,
    max_results: int,
) -> list[RankedJob]:
    user_seniority = prefs.get("seniority")
    selected: list[RankedJob] = []
    company_counts: dict[str, int] = {}
    industry_counts: dict[str, int] = {}
    adjacent_count = 0
    for job in ranked:
        if len(selected) >= max_results:
            break
        company = job.get("company", "")
        if company_counts.get(company, 0) >= COMPANY_CAP:
            continue
        industry = job.get("industry", "unknown")
        if industry != "unknown" and industry_counts.get(industry, 0) >= INDUSTRY_CAP:
            continue
        relationship = classify_relationship(
            user_seniority, job.get("seniority", "unknown")
        )
        if relationship == "adjacent_above" and adjacent_count >= ADJACENT_TIER_CAP:
            continue
        selected.append(job)
        company_counts[company] = company_counts.get(company, 0) + 1
        if industry != "unknown":
            industry_counts[industry] = industry_counts.get(industry, 0) + 1
        if relationship == "adjacent_above":
            adjacent_count += 1
    return selected
```

Update the module docstring/comment if it enumerates the caps.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_boards.py tests/agent/test_select_results.py tests/agent/test_seniority.py -v`
Expected: PASS — all new tests, plus confirm the pre-existing `test_company_cap_enforced`/`test_adjacent_tier_cap_enforced`/etc. in `test_select_results.py` still pass unchanged (their `_job()` fixtures should default `industry="unknown"`, which is unrestricted, so they're unaffected by the new cap).

- [ ] **Step 5: Run the full backend test suite**

Run: `cd apps/api && uv run pytest -q`
Expected: all tests pass (no regressions in `test_boards.py`'s pre-existing `test_fetch_all_boards_merges_and_tolerates_failure`, `test_graph.py`'s seniority/company-diversity tests, etc. — those fixtures don't set `industry`, so it defaults to `"unknown"` and stays unrestricted).

- [ ] **Step 6: Lint and format**

Run: `cd apps/api && uv run ruff check . && uv run black --check .`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add apps/api/lewis_api/agent/sources/seed.py apps/api/lewis_api/agent/state.py apps/api/lewis_api/agent/sources/boards.py apps/api/lewis_api/agent/select_results.py apps/api/tests/agent/test_boards.py apps/api/tests/agent/test_select_results.py
git commit -m "feat: static per-company industry tag + industry diversity cap in select_results"
```

---

### Task 5: Scale the seed list with live-validated, industry-tagged companies

**Files:**
- Modify: `apps/api/lewis_api/agent/sources/seed_companies.yaml`
- Create: `apps/api/scripts/validate_seed_companies.py` (one-time/rerunnable validation tool, not part of the shipped `lewis_api` package)
- Create: `apps/api/tests/agent/test_seed_companies_data.py`

**Interfaces:**
- No code-interface change — this task produces data (`seed_companies.yaml`) consumed by the already-updated `load_seed()`/`SeedEntry` from Task 4.
- `validate_seed_companies.py` is a standalone dev script: given a list of `(company, source, board_token, industry)` candidates, live-checks each against the real Greenhouse/Ashby endpoints (HTTP 200 + non-empty job list) and prints which passed/failed. It is not imported by application code and is not covered by the mocked-API test constraint in Global Constraints (it exists specifically to make real calls) — but it must still be Ruff/Black clean.

**Context:** the existing 106 rows have no `industry` field yet (Task 4's `SeedEntry.industry` defaults to `"unknown"` for them, which is safe but wastes the diversity cap added in Task 4). This task both tags the existing 106 and adds enough new, live-validated companies to comfortably exceed 300 total.

- [ ] **Step 1: Research candidate companies**

Compile a candidate list of companies plausibly hiring via public Greenhouse or Ashby boards, spanning every industry in the Global Constraints taxonomy (aim for reasonable spread, not all-devtools/fintech). Use web research (company engineering-blog "we're hiring" pages, public tech-company directories, `careers.<company>.com` redirects to `boards.greenhouse.io/<token>` or `jobs.ashbyhq.com/<token>`) to find real company names and their actual board tokens — do not guess tokens from company names without verifying. Also assign each of the existing 106 companies (read from the current `seed_companies.yaml`) an industry tag from the fixed taxonomy, based on general knowledge of each company. Target at least 300 total candidates (existing 106 re-tagged + 200+ new) before validation — validation will drop some, so err on the high side.

- [ ] **Step 2: Write the validation script**

Create `apps/api/scripts/validate_seed_companies.py`: an async script (reuse the `httpx` + `asyncio.gather` + `Semaphore` pattern from `agent/sources/boards.py` for consistency) that takes the full candidate list, hits each board's real endpoint once
(`https://boards-api.greenhouse.io/v1/boards/{token}/jobs` or
`https://api.ashbyhq.com/posting-api/job-board/{token}`), keeps only
entries returning HTTP 200 with a non-empty job list, and writes the
survivors to `seed_companies.yaml` in the existing file's format (keep
the header comment, add `industry` to the documented per-entry shape,
alphabetize or otherwise order consistently with the current file's
convention). Print a summary: candidates tried, kept, dropped (with
reason) — no silent drops.

- [ ] **Step 3: Run the validation script**

Run: `cd apps/api && uv run python scripts/validate_seed_companies.py`
This makes real network calls — expected to take a while for 300+
candidates even with concurrency. Report the actual final count
honestly in the commit message/PR description; do not pad or fabricate
entries to hit 300 if fewer validate.

- [ ] **Step 4: Write the data-quality regression test**

Create `apps/api/tests/agent/test_seed_companies_data.py`:

```python
from lewis_api.agent.sources.seed import load_seed

_VALID_INDUSTRIES = {
    "fintech", "healthtech", "devtools", "cybersecurity", "ecommerce",
    "enterprise_saas", "consumer", "ai_ml", "biotech", "media_entertainment",
    "real_estate", "logistics_supply_chain", "gaming", "edtech",
    "hardware_robotics", "climate_energy", "unknown",
}


def test_seed_list_is_large_and_well_formed():
    entries = load_seed()
    assert len(entries) >= 250  # generous floor below the 300 target
    for e in entries:
        assert e.source in ("greenhouse", "ashby")
        assert e.board_token
        assert e.company
        assert e.industry in _VALID_INDUSTRIES


def test_seed_list_has_industry_diversity():
    entries = load_seed()
    industries = {e.industry for e in entries if e.industry != "unknown"}
    assert len(industries) >= 6  # not all companies dumped into one bucket
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_seed_companies_data.py -v`
Expected: PASS. If the validated count came in below 250, lower the
floor in the test to match the honest, actually-achieved count rather
than padding the data — note the real number in the PR description
either way.

- [ ] **Step 6: Run the full backend test suite**

Run: `cd apps/api && uv run pytest -q`
Expected: all tests pass, including `test_prefilter.py`/`test_boards.py`/`test_select_results.py` from earlier tasks and every pre-existing test.

- [ ] **Step 7: Lint and format**

Run: `cd apps/api && uv run ruff check . && uv run black --check .`
Expected: no errors (covers the new script too).

- [ ] **Step 8: Commit**

```bash
git add apps/api/lewis_api/agent/sources/seed_companies.yaml apps/api/scripts/validate_seed_companies.py apps/api/tests/agent/test_seed_companies_data.py
git commit -m "feat: scale seed list with live-validated, industry-tagged companies"
```

---

### Task 6: Final verification pass

- [ ] **Step 1:** Run the full backend suite once more from a clean state: `cd apps/api && uv run pytest -q`
- [ ] **Step 2:** `cd apps/api && uv run ruff check . && uv run black --check .`
- [ ] **Step 3:** Update `status.md` — mark this work done, record the real final seed-company count and industry spread, note what remains deferred (full field taxonomy, hard/soft ambiguity confirmation, dedup resurfacing policy, additional diversify axes) per the design doc's "Explicitly deferred" section.
- [ ] **Step 4:** Push the branch and open a PR against `main` with a summary of all 6 tasks, the verification results, and a link to the design doc.
