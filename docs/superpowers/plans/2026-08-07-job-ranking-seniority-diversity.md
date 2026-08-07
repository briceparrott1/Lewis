# Job Ranking: Seniority Enforcement + Company Diversity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the ranking pipeline from showing seniority-mismatched jobs and from letting one company dominate a result set, per `docs/superpowers/specs/2026-08-07-job-ranking-seniority-diversity-design.md`.

**Architecture:** Extend the existing single LLM ranking call (`agent/rank.py`) to also classify each job's seniority (no extra LLM round-trip). Add a pure seniority-ladder classifier module and a combined greedy final-selection module (company cap + adjacent-tier cap), then wire both into `graph.py`'s `respond` node in place of the current plain score-sort-and-slice.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, pytest + pytest-asyncio, uv.

## Global Constraints

- Seniority ladder, low to high: `intern < new_grad < mid < senior < staff`.
- Exact seniority tier match: always eligible, uncapped.
- One tier above the user's level: eligible, capped at **3** of the final results.
- One tier below, or 2+ tiers away in either direction: hard-excluded.
- `seniority == "unknown"`: always eligible, uncapped, not counted toward the adjacent-tier cap.
- No seniority filtering at all when the user's `prefs["seniority"]` is unset.
- Company diversity cap: at most **2** jobs from the same company in the final results.
- `max_results` (final result count): **7** (was 6).
- On invalid/missing `seniority` from the LLM ranking response: fail open to `"unknown"`, never raise or drop the job.
- Python style: PEP 8, Black-formatted (88 cols), Ruff-clean (`ruff check .`), type hints on public APIs (per project/global CLAUDE.md).
- Tests use the existing `FakeLLM` mocking pattern already present in `tests/agent/test_rank.py` / `tests/agent/test_graph.py` — never call the real Anthropic API in tests.

---

### Task 1: Classify job seniority in the ranking LLM call

**Files:**
- Modify: `apps/api/lewis_api/agent/rank.py:6-23` (`_SCHEMA`), `apps/api/lewis_api/agent/rank.py:25-30` (`_SYSTEM`), `apps/api/lewis_api/agent/rank.py:33-67` (`rank_jobs`)
- Modify: `apps/api/lewis_api/agent/state.py:28-30` (`RankedJob`)
- Test: `apps/api/tests/agent/test_rank.py`

**Interfaces:**
- Produces: `RankedJob` now includes `seniority: Literal["intern", "new_grad", "mid", "senior", "staff", "unknown"]`. `rank_jobs(candidates, prefs, resume_text, llm) -> list[RankedJob]` signature is unchanged; every returned job now always has a valid `seniority` value (never missing, never an invalid string).

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/agent/test_rank.py`:

```python
@pytest.mark.asyncio
async def test_rank_includes_seniority_and_falls_back_to_unknown():
    cands = [
        {"external_id": "1", "title": "New Grad SWE", "url": "u1", "description": "x"},
        {"external_id": "2", "title": "Staff Engineer", "url": "u2", "description": "y"},
        {"external_id": "3", "title": "Engineer", "url": "u3", "description": "z"},
    ]
    llm = FakeLLM(
        {
            "rankings": [
                {
                    "external_id": "1",
                    "score": 60,
                    "reason": "ok",
                    "seniority": "new_grad",
                },
                {
                    "external_id": "2",
                    "score": 95,
                    "reason": "great",
                    "seniority": "bogus-value",  # invalid -> falls back
                },
                {
                    "external_id": "3",
                    "score": 40,
                    "reason": "meh",
                    # no "seniority" key at all -> falls back
                },
            ]
        }
    )
    out = await rank_jobs(cands, {}, "resume", llm)
    by_id = {j["external_id"]: j for j in out}
    assert by_id["1"]["seniority"] == "new_grad"
    assert by_id["2"]["seniority"] == "unknown"
    assert by_id["3"]["seniority"] == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/agent/test_rank.py::test_rank_includes_seniority_and_falls_back_to_unknown -v`
Expected: FAIL with `KeyError: 'seniority'` (the field doesn't exist on returned jobs yet).

- [ ] **Step 3: Extend the schema, prompt, and RankedJob type**

In `apps/api/lewis_api/agent/rank.py`, replace `_SCHEMA` and `_SYSTEM`:

```python
_VALID_SENIORITY = {"intern", "new_grad", "mid", "senior", "staff", "unknown"}

_SCHEMA = {
    "type": "object",
    "properties": {
        "rankings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "external_id": {"type": "string"},
                    "score": {"type": "integer"},
                    "reason": {"type": "string"},
                    "seniority": {
                        "type": "string",
                        "enum": [
                            "intern",
                            "new_grad",
                            "mid",
                            "senior",
                            "staff",
                            "unknown",
                        ],
                    },
                },
                "required": ["external_id", "score", "reason", "seniority"],
            },
        }
    },
    "required": ["rankings"],
}

_SYSTEM = (
    "Score each candidate job 0-100 for how well it fits the user's resume and "
    "preferences. Trade off soft preferences in the order given by 'priorities' "
    "(most important first); never violate a 'required' dimension. Give a concise "
    "one-line reason per job, citing tradeoffs where relevant. Also classify each "
    "job's seniority level as one of intern, new_grad, mid, senior, or staff, based "
    "only on explicit signals in its title or description (e.g. 'Senior', 'New Grad', "
    "'Staff', years-of-experience ranges). If the title and description give no clear "
    "seniority signal, classify it as unknown rather than guessing."
)
```

In `apps/api/lewis_api/agent/state.py`, update `RankedJob`:

```python
class RankedJob(Job, total=False):
    score: int
    reason: str
    seniority: Literal["intern", "new_grad", "mid", "senior", "staff", "unknown"]
```

In `apps/api/lewis_api/agent/rank.py`, update the loop inside `rank_jobs`:

```python
    by_id = {r["external_id"]: r for r in result.get("rankings", [])}
    ranked: list[RankedJob] = []
    for c in candidates:
        r = by_id.get(c.get("external_id"), {})
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
Expected: PASS (both the new test and the existing `test_rank_merges_and_sorts`).

- [ ] **Step 5: Lint and format**

Run: `cd apps/api && uv run ruff check . && uv run black --check .`
Expected: no errors. If Black reports formatting issues, run `uv run black .` and re-check.

- [ ] **Step 6: Commit**

```bash
git add apps/api/lewis_api/agent/rank.py apps/api/lewis_api/agent/state.py apps/api/tests/agent/test_rank.py
git commit -m "feat: classify job seniority in the ranking LLM call"
```

---

### Task 2: Seniority ladder classifier

**Files:**
- Create: `apps/api/lewis_api/agent/seniority.py`
- Test: `apps/api/tests/agent/test_seniority.py`

**Interfaces:**
- Consumes: `RankedJob` (has `seniority` field per Task 1), `StructuredPrefs` (has `seniority` field, from `apps/api/lewis_api/agent/state.py`).
- Produces: `classify_relationship(user_seniority: str | None, job_seniority: str) -> str` returning one of `"exact"`, `"adjacent_above"`, `"exclude"`, `"unrestricted"`. `filter_by_seniority(ranked: list[RankedJob], prefs: StructuredPrefs) -> list[RankedJob]`, used by Task 4.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/agent/test_seniority.py`:

```python
import pytest

from lewis_api.agent.seniority import classify_relationship, filter_by_seniority


@pytest.mark.parametrize(
    "user_level,job_level,expected",
    [
        ("mid", "mid", "exact"),
        ("mid", "senior", "adjacent_above"),
        ("mid", "new_grad", "exclude"),  # one tier below
        ("mid", "staff", "exclude"),  # two tiers above
        ("mid", "intern", "exclude"),  # two tiers below
        ("mid", "unknown", "unrestricted"),
        (None, "intern", "unrestricted"),
        ("staff", "staff", "exact"),  # top of ladder, no tier above
    ],
)
def test_classify_relationship(user_level, job_level, expected):
    assert classify_relationship(user_level, job_level) == expected


def test_filter_by_seniority_drops_only_excluded():
    ranked = [
        {"external_id": "1", "seniority": "mid"},  # exact -> kept
        {"external_id": "2", "seniority": "senior"},  # adjacent above -> kept
        {"external_id": "3", "seniority": "new_grad"},  # one below -> dropped
        {"external_id": "4", "seniority": "staff"},  # two above -> dropped
        {"external_id": "5", "seniority": "unknown"},  # kept
    ]
    out = filter_by_seniority(ranked, {"seniority": "mid"})
    assert [j["external_id"] for j in out] == ["1", "2", "5"]


def test_filter_by_seniority_noop_when_prefs_unset():
    ranked = [{"external_id": "1", "seniority": "intern"}]
    out = filter_by_seniority(ranked, {})
    assert out == ranked
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/agent/test_seniority.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lewis_api.agent.seniority'`.

- [ ] **Step 3: Write the implementation**

Create `apps/api/lewis_api/agent/seniority.py`:

```python
from lewis_api.agent.state import RankedJob, StructuredPrefs

LADDER = ["intern", "new_grad", "mid", "senior", "staff"]


def classify_relationship(user_seniority: str | None, job_seniority: str) -> str:
    """Classify a job's seniority relative to the user's stated level.

    Returns "exact", "adjacent_above", "exclude", or "unrestricted".
    "unrestricted" covers both an unset user preference and an
    unclassifiable ("unknown") job -- neither case has enough signal to
    filter or cap on.
    """
    if not user_seniority or job_seniority == "unknown":
        return "unrestricted"
    if job_seniority not in LADDER or user_seniority not in LADDER:
        return "unrestricted"
    diff = LADDER.index(job_seniority) - LADDER.index(user_seniority)
    if diff == 0:
        return "exact"
    if diff == 1:
        return "adjacent_above"
    return "exclude"


def filter_by_seniority(
    ranked: list[RankedJob], prefs: StructuredPrefs
) -> list[RankedJob]:
    """Drop jobs one tier below, or 2+ tiers away, from the user's seniority."""
    user_seniority = prefs.get("seniority")
    return [
        job
        for job in ranked
        if classify_relationship(user_seniority, job.get("seniority", "unknown"))
        != "exclude"
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_seniority.py -v`
Expected: PASS (all parametrized cases and both `filter_by_seniority` tests).

- [ ] **Step 5: Lint and format**

Run: `cd apps/api && uv run ruff check . && uv run black --check .`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add apps/api/lewis_api/agent/seniority.py apps/api/tests/agent/test_seniority.py
git commit -m "feat: seniority ladder classifier for hard-exclusion filtering"
```

---

### Task 3: Combined final-selection algorithm (company + adjacent-tier caps)

**Files:**
- Create: `apps/api/lewis_api/agent/select_results.py`
- Test: `apps/api/tests/agent/test_select_results.py`

**Interfaces:**
- Consumes: `classify_relationship(user_seniority, job_seniority) -> str` from Task 2 (`apps/api/lewis_api/agent/seniority.py`). `RankedJob`, `StructuredPrefs` from `apps/api/lewis_api/agent/state.py`.
- Produces: `select_results(ranked: list[RankedJob], prefs: StructuredPrefs, max_results: int) -> list[RankedJob]`, used by Task 4. **Precondition:** `ranked` must already be sorted by score descending and already hard-filtered via `filter_by_seniority` (Task 2) — this function only enforces the company cap and the adjacent-tier cap, not hard exclusion.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/agent/test_select_results.py`:

```python
from lewis_api.agent.select_results import select_results


def _job(id_, company, score, seniority="unknown"):
    return {
        "external_id": id_,
        "company": company,
        "score": score,
        "seniority": seniority,
    }


def test_company_cap_enforced():
    ranked = [
        _job("1", "Acme", 99),
        _job("2", "Acme", 98),
        _job("3", "Acme", 97),  # would be 3rd Acme -> skipped
        _job("4", "Beta", 50),
    ]
    out = select_results(ranked, {}, max_results=4)
    assert [j["external_id"] for j in out] == ["1", "2", "4"]


def test_adjacent_tier_cap_enforced():
    ranked = [
        _job("1", "A", 99, "senior"),
        _job("2", "B", 98, "senior"),
        _job("3", "C", 97, "senior"),
        _job("4", "D", 96, "senior"),  # 4th adjacent-above -> skipped
        _job("5", "E", 50, "mid"),  # exact match, doesn't consume the cap
    ]
    out = select_results(ranked, {"seniority": "mid"}, max_results=5)
    assert [j["external_id"] for j in out] == ["1", "2", "3", "5"]


def test_prefers_highest_score_among_eligible():
    ranked = [_job("1", "A", 90), _job("2", "B", 95), _job("3", "C", 80)]
    out = select_results(ranked, {}, max_results=2)
    assert [j["external_id"] for j in out] == ["2", "1"]


def test_stops_at_max_results():
    ranked = [_job(str(i), f"Co{i}", 100 - i) for i in range(10)]
    out = select_results(ranked, {}, max_results=3)
    assert len(out) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/agent/test_select_results.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lewis_api.agent.select_results'`.

- [ ] **Step 3: Write the implementation**

Create `apps/api/lewis_api/agent/select_results.py`:

```python
from lewis_api.agent.seniority import classify_relationship
from lewis_api.agent.state import RankedJob, StructuredPrefs

COMPANY_CAP = 2
ADJACENT_TIER_CAP = 3


def select_results(
    ranked: list[RankedJob],
    prefs: StructuredPrefs,
    max_results: int,
) -> list[RankedJob]:
    """Greedily build the final results, honoring the per-company cap and
    the adjacent-seniority-tier cap. `ranked` must already be sorted by
    score descending and hard-excluded via seniority.filter_by_seniority.
    """
    user_seniority = prefs.get("seniority")
    selected: list[RankedJob] = []
    company_counts: dict[str, int] = {}
    adjacent_count = 0
    for job in ranked:
        if len(selected) >= max_results:
            break
        company = job.get("company", "")
        if company_counts.get(company, 0) >= COMPANY_CAP:
            continue
        relationship = classify_relationship(
            user_seniority, job.get("seniority", "unknown")
        )
        if relationship == "adjacent_above" and adjacent_count >= ADJACENT_TIER_CAP:
            continue
        selected.append(job)
        company_counts[company] = company_counts.get(company, 0) + 1
        if relationship == "adjacent_above":
            adjacent_count += 1
    return selected
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_select_results.py -v`
Expected: PASS (all 4 tests).

- [ ] **Step 5: Lint and format**

Run: `cd apps/api && uv run ruff check . && uv run black --check .`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add apps/api/lewis_api/agent/select_results.py apps/api/tests/agent/test_select_results.py
git commit -m "feat: combined company-diversity and adjacent-tier selection cap"
```

---

### Task 4: Wire selection into the graph and bump max_results

**Files:**
- Modify: `apps/api/lewis_api/config.py:17`
- Modify: `apps/api/lewis_api/agent/graph.py:1-11` (imports), `apps/api/lewis_api/agent/graph.py:57-62` (`respond`)
- Test: `apps/api/tests/agent/test_graph.py`

**Interfaces:**
- Consumes: `filter_by_seniority(ranked, prefs) -> list[RankedJob]` (Task 2), `select_results(ranked, prefs, max_results) -> list[RankedJob]` (Task 3), `get_settings().max_results` (`apps/api/lewis_api/config.py`).

- [ ] **Step 1: Write the failing tests**

Add to `apps/api/tests/agent/test_graph.py`:

```python
@pytest.mark.asyncio
async def test_respond_applies_company_diversity_cap():
    async def fetch_many(entries, client):
        jobs = [
            {
                "source": "greenhouse",
                "company": "Acme",
                "board_token": "acme",
                "external_id": f"acme-{i}",
                "title": "Software Engineer",
                "location": "SF",
                "url": f"https://boards.greenhouse.io/acme/{i}",
                "description": "d",
            }
            for i in range(4)
        ]
        jobs.append(
            {
                "source": "ashby",
                "company": "Beta",
                "board_token": "beta",
                "external_id": "beta-1",
                "title": "Software Engineer",
                "location": "SF",
                "url": "https://jobs.ashbyhq.com/beta/1",
                "description": "d",
            }
        )
        return jobs

    rank_payload = {
        "rankings": [
            {
                "external_id": f"acme-{i}",
                "score": 90 - i,
                "reason": "x",
                "seniority": "unknown",
            }
            for i in range(4)
        ]
        + [
            {
                "external_id": "beta-1",
                "score": 50,
                "reason": "x",
                "seniority": "unknown",
            }
        ]
    }
    llm = FakeLLM(
        {"role_keywords": ["engineer"], "locations": ["SF"], "required": ["role"]},
        rank_payload,
    )
    seed = [SeedEntry("Acme", "greenhouse", "acme")]
    graph = build_graph(llm, fetch_many, seed, MemorySaver())
    events = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            served_keys=[],
            message="SWE in SF",
            thread_id="u1:c4",
        )
    ]
    results = [e["job"] for e in events if e["type"] == "result"]
    companies = [j["company"] for j in results]
    assert companies.count("Acme") <= 2
    assert "Beta" in companies


@pytest.mark.asyncio
async def test_respond_excludes_seniority_mismatch():
    async def fetch_two(entries, client):
        return [
            {
                "source": "greenhouse",
                "company": "Acme",
                "board_token": "acme",
                "external_id": "senior-role",
                "title": "Senior Software Engineer",
                "location": "SF",
                "url": "https://boards.greenhouse.io/acme/1",
                "description": "d",
            },
            {
                "source": "greenhouse",
                "company": "Acme",
                "board_token": "acme",
                "external_id": "mid-role",
                "title": "Mid-level Software Engineer",
                "location": "SF",
                "url": "https://boards.greenhouse.io/acme/2",
                "description": "d",
            },
        ]

    rank_payload = {
        "rankings": [
            {
                "external_id": "senior-role",
                "score": 90,
                "reason": "x",
                "seniority": "senior",
            },
            {
                "external_id": "mid-role",
                "score": 80,
                "reason": "x",
                "seniority": "mid",  # one tier below "senior" -> excluded
            },
        ]
    }
    llm = FakeLLM(
        {
            "role_keywords": ["engineer"],
            "locations": ["SF"],
            "required": ["role"],
            "seniority": "senior",
        },
        rank_payload,
    )
    seed = [SeedEntry("Acme", "greenhouse", "acme")]
    graph = build_graph(llm, fetch_two, seed, MemorySaver())
    events = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            served_keys=[],
            message="senior SWE in SF",
            thread_id="u1:c5",
        )
    ]
    results = [e["job"] for e in events if e["type"] == "result"]
    assert [j["external_id"] for j in results] == ["senior-role"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/agent/test_graph.py -v`
Expected: `test_respond_applies_company_diversity_cap` FAILs (all 5 jobs returned, 4 from Acme). `test_respond_excludes_seniority_mismatch` FAILs (`mid-role` still present in results).

- [ ] **Step 3: Bump max_results**

In `apps/api/lewis_api/config.py`, change line 17:

```python
    max_results: int = 7
```

- [ ] **Step 4: Wire the new filtering/selection into `respond`**

In `apps/api/lewis_api/agent/graph.py`, add imports after the existing `from lewis_api.agent.rank import rank_jobs` line:

```python
from lewis_api.agent.select_results import select_results
from lewis_api.agent.seniority import filter_by_seniority
```

Replace the `respond` function body:

```python
    async def respond(state: AgentState) -> dict:
        writer = get_stream_writer()
        eligible = filter_by_seniority(state.get("ranked", []), state["prefs"])
        top = select_results(eligible, state["prefs"], get_settings().max_results)
        for job in top:
            writer({"type": "result", "job": job})
        return {"ranked": top}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_graph.py -v`
Expected: PASS (all tests in the file, including the two new ones and the three pre-existing ones).

- [ ] **Step 6: Run the full test suite**

Run: `cd apps/api && uv run pytest -q`
Expected: all tests pass (34 pre-existing + new tests from Tasks 1-4), 0 failures.

- [ ] **Step 7: Lint and format**

Run: `cd apps/api && uv run ruff check . && uv run black --check .`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add apps/api/lewis_api/config.py apps/api/lewis_api/agent/graph.py apps/api/tests/agent/test_graph.py
git commit -m "feat: wire seniority filtering and diversity cap into the agent graph"
```
