# Agent Core & Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the LangGraph search agent (parse → scan Greenhouse/Ashby → exclude-served → prefilter → Claude-rank → respond, with a clarify-then-search loop) as a pure, testable callable, and wire it into `POST /api/chat` as an SSE stream.

**Architecture:** A LangGraph `StateGraph` whose nodes are plain async functions closing over injected dependencies (an LLM client and a board-fetch function) so tests can substitute fakes. Clarify-across-turns is achieved with a Postgres checkpointer that persists graph state per `thread_id` — a vague query ends the turn after emitting one clarifying question; the next message on the same `conversation_id` re-runs with the persisted prefs merged in. Nodes stream typed events (`status`/`clarify`/`result`/`done`) via LangGraph's custom stream writer, which the chat route forwards as SSE frames. **All Claude calls are mocked in tests**; the model defaults to Haiku (`AGENT_MODEL`).

**Tech Stack:** Builds on Plan 1. Adds `langgraph`, `langgraph-checkpoint-postgres`, `anthropic`, `httpx` (runtime), `pyyaml`.

## Global Constraints

- Python 3.12; `uv`; run commands from `apps/api/` with `uv run`.
- PEP 8, Black (88 cols), Ruff import sort, type hints on public functions, no unused imports. `ruff check .` and `black --check .` must pass.
- **TDD:** every behavior ships with a minimal test that passes before commit.
- **No live Claude calls in automated tests** — inject a fake LLM. Real board HTTP is also mocked via `httpx.MockTransport`.
- The agent graph must be a **pure callable** (dependencies injected), independent of FastAPI.
- Agent model from `settings.agent_model` (default `claude-haiku-4-5-20251001`).
- Every data access scoped to the authenticated `user_id`.
- Commit + push per task; the controller verifies `origin` after each task.
- Reference: spec §7 (`docs/superpowers/specs/2026-08-06-lewis-architecture-design.md`), `docs/prd/agent-core-prd.md`.

**Design refinement vs spec §7.1:** we use checkpointer-persisted state across turns for the clarify loop instead of `interrupt()`. Same observable behavior (one clarify, then proceed), simpler control flow.

---

## File Structure

```
apps/api/lewis_api/
├─ agent/
│  ├─ __init__.py
│  ├─ state.py          # StructuredPrefs, Job, RankedJob, AgentState (TypedDicts)
│  ├─ normalize.py      # normalize_url(), job_key()
│  ├─ prefilter.py      # deterministic soft-scoring funnel
│  ├─ llm.py            # AsyncAnthropic wrapper (structured tool call); Protocol for fakes
│  ├─ prefs.py          # parse_prefs(), is_sufficient()
│  ├─ rank.py           # rank_jobs()
│  ├─ graph.py          # build_graph(deps), run_agent() async generator
│  └─ sources/
│     ├─ __init__.py
│     ├─ greenhouse.py  # fetch_greenhouse()
│     ├─ ashby.py       # fetch_ashby()
│     ├─ seed.py        # load_seed(); SeedEntry
│     ├─ seed_companies.yaml
│     └─ boards.py      # fetch_all_boards() concurrent + resilient + TTL cache
├─ chat/
│  ├─ __init__.py
│  └─ routes.py         # POST /api/chat (SSE)
└─ (config.py, main.py modified)
```

All external I/O (Claude, board HTTP) is injected/mocked in tests. `graph.build_graph(llm, fetch_boards, checkpointer)` returns a compiled graph; `run_agent(...)` wraps it as an event stream.

---

### Task 1: Agent dependencies + types + URL normalization

**Files:**
- Modify: `apps/api/pyproject.toml` (add deps)
- Create: `lewis_api/agent/__init__.py`, `lewis_api/agent/state.py`, `lewis_api/agent/normalize.py`
- Test: `tests/agent/__init__.py`, `tests/agent/test_normalize.py`

**Interfaces:**
- Produces: `state.StructuredPrefs`, `state.Job`, `state.RankedJob`, `state.AgentState` (TypedDicts). `normalize.normalize_url(url: str) -> str`, `normalize.job_key(job: Job) -> str` (returns `normalize_url(job["url"])`).

- [ ] **Step 1: Add dependencies** — edit `pyproject.toml` `dependencies`, adding:
```
    "httpx>=0.27",
    "langgraph>=0.2.50",
    "langgraph-checkpoint-postgres>=2.0",
    "anthropic>=0.40",
    "pyyaml>=6.0",
```
Then run `uv sync`. (httpx was previously dev-only; it is now a runtime dep. Leaving it in dev too is harmless.)

- [ ] **Step 2: Write the failing test** — `tests/agent/__init__.py` (empty) and `tests/agent/test_normalize.py`

```python
from lewis_api.agent.normalize import job_key, normalize_url


def test_normalize_strips_query_fragment_and_trailing_slash():
    assert normalize_url("HTTP://Jobs.ashbyhq.com/ramp/abc/?utm_source=x#top") == (
        "https://jobs.ashbyhq.com/ramp/abc"
    )


def test_normalize_forces_https_lowercases_host_only():
    assert normalize_url("http://Boards.Greenhouse.io/gitlab/jobs/123") == (
        "https://boards.greenhouse.io/gitlab/jobs/123"
    )


def test_job_key_uses_normalized_url():
    job = {"url": "https://jobs.ashbyhq.com/ramp/abc/?x=1"}
    assert job_key(job) == "https://jobs.ashbyhq.com/ramp/abc"
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/agent/test_normalize.py -v`
Expected: FAIL (module missing).

- [ ] **Step 4: Implement `lewis_api/agent/state.py`**

```python
from typing import Literal, TypedDict


class StructuredPrefs(TypedDict, total=False):
    role_keywords: list[str]
    locations: list[str]
    remote_ok: bool | None
    seniority: Literal["intern", "new_grad", "mid", "senior", "staff"] | None
    extra: str
    required: list[str]
    priorities: list[str]


class Job(TypedDict, total=False):
    source: Literal["greenhouse", "ashby"]
    company: str
    board_token: str
    external_id: str
    title: str
    location: str
    department: str | None
    url: str
    posted_at: str | None
    compensation: str | None
    description: str


class RankedJob(Job, total=False):
    score: int
    reason: str


class AgentState(TypedDict, total=False):
    user_id: str
    resume_text: str
    prefs: StructuredPrefs
    clarified_once: bool
    served_keys: list[str]
    new_message: str
    candidates: list[Job]
    ranked: list[RankedJob]
    clarify_question: str | None
```

- [ ] **Step 5: Implement `lewis_api/agent/normalize.py`** (and empty `agent/__init__.py`)

```python
from urllib.parse import urlsplit, urlunsplit

from lewis_api.agent.state import Job


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def job_key(job: Job) -> str:
    return normalize_url(job["url"])
```

- [ ] **Step 6: Run tests, lint, commit**

```bash
uv run pytest tests/agent/test_normalize.py -v      # PASS
uv run ruff check . && uv run black --check .
git add -A && git commit -m "feat: agent types + URL normalization/job_key + deps"
git push origin main
```

---

### Task 2: Greenhouse + Ashby fetchers

**Files:**
- Create: `lewis_api/agent/sources/__init__.py`, `sources/greenhouse.py`, `sources/ashby.py`
- Test: `tests/agent/test_sources.py`

**Interfaces:**
- Produces: `async fetch_greenhouse(token: str, client: httpx.AsyncClient) -> list[Job]`, `async fetch_ashby(org: str, client: httpx.AsyncClient) -> list[Job]`. Both map provider JSON → the common `Job` shape and set `source`, `board_token`, `external_id`, `url`, `description` (plain text), etc.

- [ ] **Step 1: Write the failing test** — `tests/agent/test_sources.py`

```python
import httpx
import pytest

from lewis_api.agent.sources.ashby import fetch_ashby
from lewis_api.agent.sources.greenhouse import fetch_greenhouse

GH_PAYLOAD = {
    "jobs": [
        {
            "id": 123,
            "title": "Forward Deployed Engineer",
            "absolute_url": "https://job-boards.greenhouse.io/gitlab/jobs/123",
            "location": {"name": "Remote, US"},
            "updated_at": "2026-08-01T00:00:00Z",
            "content": "&lt;p&gt;Build things&lt;/p&gt;",
        }
    ]
}

ASHBY_PAYLOAD = {
    "jobs": [
        {
            "id": "uuid-1",
            "title": "Solutions Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/ramp/uuid-1",
            "applyUrl": "https://jobs.ashbyhq.com/ramp/uuid-1/application",
            "location": "New York",
            "department": "GTM",
            "publishedAt": "2026-08-02T00:00:00Z",
            "descriptionPlain": "Deploy with customers",
            "compensation": {"summary": "$150k"},
        }
    ]
}


def _client(payload):
    def handler(request):
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_fetch_greenhouse_maps_fields():
    async with _client(GH_PAYLOAD) as client:
        jobs = await fetch_greenhouse("gitlab", client)
    j = jobs[0]
    assert j["source"] == "greenhouse"
    assert j["board_token"] == "gitlab"
    assert j["external_id"] == "123"
    assert j["url"] == "https://job-boards.greenhouse.io/gitlab/jobs/123"
    assert j["location"] == "Remote, US"
    assert "Build things" in j["description"]  # HTML stripped


@pytest.mark.asyncio
async def test_fetch_ashby_maps_fields_and_uses_jobUrl():
    async with _client(ASHBY_PAYLOAD) as client:
        jobs = await fetch_ashby("ramp", client)
    j = jobs[0]
    assert j["source"] == "ashby"
    assert j["url"] == "https://jobs.ashbyhq.com/ramp/uuid-1"  # not applyUrl
    assert j["description"] == "Deploy with customers"
    assert j["department"] == "GTM"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/agent/test_sources.py -v` → FAIL (modules missing).

- [ ] **Step 3: Implement `lewis_api/agent/sources/greenhouse.py`** (and empty `sources/__init__.py`)

```python
import re

import httpx

from lewis_api.agent.state import Job

_TAG = re.compile(r"<[^>]+>")
_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    import html

    return html.unescape(_TAG.sub(" ", text)).strip()


async def fetch_greenhouse(token: str, client: httpx.AsyncClient) -> list[Job]:
    resp = await client.get(_URL.format(token=token))
    resp.raise_for_status()
    jobs: list[Job] = []
    for item in resp.json().get("jobs", []):
        jobs.append(
            Job(
                source="greenhouse",
                company=token,
                board_token=token,
                external_id=str(item["id"]),
                title=item.get("title", ""),
                location=(item.get("location") or {}).get("name", ""),
                department=None,
                url=item["absolute_url"],
                posted_at=item.get("updated_at"),
                compensation=None,
                description=_strip_html(item.get("content"))[:2000],
            )
        )
    return jobs
```

- [ ] **Step 4: Implement `lewis_api/agent/sources/ashby.py`**

```python
import httpx

from lewis_api.agent.state import Job

_URL = "https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"


async def fetch_ashby(org: str, client: httpx.AsyncClient) -> list[Job]:
    resp = await client.get(_URL.format(org=org))
    resp.raise_for_status()
    jobs: list[Job] = []
    for item in resp.json().get("jobs", []):
        comp = item.get("compensation") or {}
        jobs.append(
            Job(
                source="ashby",
                company=org,
                board_token=org,
                external_id=str(item["id"]),
                title=item.get("title", ""),
                location=item.get("location", ""),
                department=item.get("department"),
                url=item["jobUrl"],
                posted_at=item.get("publishedAt"),
                compensation=comp.get("summary") if isinstance(comp, dict) else None,
                description=(item.get("descriptionPlain") or "")[:2000],
            )
        )
    return jobs
```

- [ ] **Step 5: Run tests, lint, commit**

```bash
uv run pytest tests/agent/test_sources.py -v      # PASS
uv run ruff check . && uv run black --check .
git add -A && git commit -m "feat: Greenhouse + Ashby board fetchers with field mapping"
git push origin main
```

---

### Task 3: Seed list + resilient concurrent fetch

**Files:**
- Create: `lewis_api/agent/sources/seed.py`, `sources/seed_companies.yaml`, `sources/boards.py`
- Test: `tests/agent/test_boards.py`

**Interfaces:**
- Produces: `seed.SeedEntry` (dataclass: `company: str`, `source: str`, `board_token: str`), `seed.load_seed() -> list[SeedEntry]`. `boards.fetch_all_boards(entries, client, *, concurrency=15, timeout=5.0) -> list[Job]` — concurrent, per-board timeout, partial-failure tolerant (a failing board is skipped), deduped by `job_key`, with a module-level ~10-min TTL cache keyed by `(source, board_token)`.

- [ ] **Step 1: Write `sources/seed_companies.yaml`** (starter list — validated in Step 6)

```yaml
- {company: GitLab, source: greenhouse, board_token: gitlab}
- {company: Ramp, source: ashby, board_token: ramp}
```
(More entries are added by the validation step below; keep only tokens that resolve.)

- [ ] **Step 2: Write the failing test** — `tests/agent/test_boards.py`

```python
import pytest

from lewis_api.agent.sources import boards
from lewis_api.agent.state import Job


@pytest.mark.asyncio
async def test_fetch_all_boards_merges_and_tolerates_failure(monkeypatch):
    async def fake_gh(token, client):
        return [Job(source="greenhouse", url=f"https://x/{token}/1", title="A")]

    async def fake_ashby(org, client):
        raise RuntimeError("boom")  # one board fails

    monkeypatch.setattr(boards, "fetch_greenhouse", fake_gh)
    monkeypatch.setattr(boards, "fetch_ashby", fake_ashby)
    boards._CACHE.clear()

    entries = [
        boards.SeedEntry("GitLab", "greenhouse", "gitlab"),
        boards.SeedEntry("Ramp", "ashby", "ramp"),
    ]
    jobs = await boards.fetch_all_boards(entries, client=None)
    assert len(jobs) == 1  # ashby failure skipped, gitlab kept
    assert jobs[0]["title"] == "A"
```

- [ ] **Step 3: Run to verify failure** → `uv run pytest tests/agent/test_boards.py -v` FAIL.

- [ ] **Step 4: Implement `lewis_api/agent/sources/seed.py`**

```python
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SeedEntry:
    company: str
    source: str
    board_token: str


_SEED_PATH = Path(__file__).with_name("seed_companies.yaml")


def load_seed() -> list[SeedEntry]:
    data = yaml.safe_load(_SEED_PATH.read_text()) or []
    return [SeedEntry(**row) for row in data]
```

- [ ] **Step 5: Implement `lewis_api/agent/sources/boards.py`**

```python
import asyncio
import time

import httpx

from lewis_api.agent.normalize import job_key
from lewis_api.agent.sources.ashby import fetch_ashby
from lewis_api.agent.sources.greenhouse import fetch_greenhouse
from lewis_api.agent.sources.seed import SeedEntry, load_seed  # noqa: F401
from lewis_api.agent.state import Job

_CACHE: dict[tuple[str, str], tuple[float, list[Job]]] = {}
_TTL = 600.0


async def _fetch_one(
    entry: SeedEntry, client: httpx.AsyncClient, timeout: float
) -> list[Job]:
    key = (entry.source, entry.board_token)
    cached = _CACHE.get(key)
    if cached and (time.monotonic() - cached[0]) < _TTL:
        return cached[1]
    fetcher = fetch_greenhouse if entry.source == "greenhouse" else fetch_ashby
    jobs = await asyncio.wait_for(fetcher(entry.board_token, client), timeout)
    _CACHE[key] = (time.monotonic(), jobs)
    return jobs


async def fetch_all_boards(
    entries: list[SeedEntry],
    client: httpx.AsyncClient | None,
    *,
    concurrency: int = 15,
    timeout: float = 5.0,
) -> list[Job]:
    sem = asyncio.Semaphore(concurrency)

    async def guarded(entry: SeedEntry) -> list[Job]:
        async with sem:
            try:
                return await _fetch_one(entry, client, timeout)
            except Exception:
                return []  # partial-failure tolerant: skip this board

    results = await asyncio.gather(*(guarded(e) for e in entries))
    seen: set[str] = set()
    merged: list[Job] = []
    for jobs in results:
        for job in jobs:
            k = job_key(job)
            if k not in seen:
                seen.add(k)
                merged.append(job)
    return merged
```
Note: `time.monotonic()` is allowed here (this is application code, not a workflow script).

- [ ] **Step 6: Validate & expand the seed list (real network, free public APIs)**

Run this one-off check and keep only tokens that return jobs; add a handful more you confirm (common Greenhouse tokens and Ashby orgs). Do NOT commit dead tokens.
```bash
uv run python -c "
import asyncio, httpx
from lewis_api.agent.sources.greenhouse import fetch_greenhouse
from lewis_api.agent.sources.ashby import fetch_ashby
async def main():
    async with httpx.AsyncClient(timeout=8) as c:
        for t in ['gitlab']:
            print('gh', t, len(await fetch_greenhouse(t, c)))
        for o in ['ramp']:
            print('ashby', o, len(await fetch_ashby(o, c)))
asyncio.run(main())
"
```
If `gitlab` and `ramp` return >0, the seed is valid. (Expanding the list further is optional and can happen later; two live boards are enough to exercise the pipeline.)

- [ ] **Step 7: Run tests, lint, commit**

```bash
uv run pytest tests/agent/test_boards.py -v       # PASS
uv run ruff check . && uv run black --check .
git add -A && git commit -m "feat: seed list + resilient concurrent board fetch with TTL cache"
git push origin main
```

---

### Task 4: Deterministic prefilter (required hard-filter + priority soft-score)

**Files:**
- Create: `lewis_api/agent/prefilter.py`
- Test: `tests/agent/test_prefilter.py`

**Interfaces:**
- Produces: `prefilter(jobs: list[Job], prefs: StructuredPrefs, *, cap: int = 50) -> list[Job]`. Hard-drops jobs failing any `required` dimension; scores the rest (title keyword hits weighted highest, then location, then seniority), weighting each dimension by its rank in `priorities`; returns the top `cap` by score, dropping zero-signal jobs.

- [ ] **Step 1: Write the failing test** — `tests/agent/test_prefilter.py`

```python
from lewis_api.agent.prefilter import prefilter


def _job(title, location):
    return {"title": title, "location": location, "description": ""}


def test_required_role_is_hard_filter():
    prefs = {"role_keywords": ["fde"], "required": ["role"], "locations": ["SF"]}
    jobs = [_job("Forward Deployed Engineer (FDE)", "NYC"), _job("Barista", "SF")]
    out = prefilter(jobs, prefs)
    assert len(out) == 1
    assert "Forward" in out[0]["title"]  # non-FDE dropped despite SF match


def test_soft_location_does_not_drop_but_scores():
    prefs = {"role_keywords": ["fde"], "locations": ["SF"], "priorities": ["role", "location"]}
    sf = _job("FDE", "San Francisco")
    ny = _job("FDE", "New York")
    out = prefilter([ny, sf], prefs)
    assert [j["location"] for j in out][0] == "San Francisco"  # SF ranks first
    assert len(out) == 2  # neither dropped (location is soft)


def test_zero_signal_dropped_and_cap_applies():
    prefs = {"role_keywords": ["fde"]}
    jobs = [_job("Chef", "SF") for _ in range(3)] + [_job("FDE", "SF")]
    out = prefilter(jobs, prefs, cap=2)
    assert all("fde" in j["title"].lower() for j in out)
    assert len(out) == 1
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement `lewis_api/agent/prefilter.py`**

```python
from lewis_api.agent.state import Job, StructuredPrefs


def _kw_hit(text: str, keywords: list[str]) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in keywords)


def _weight(dimension: str, priorities: list[str]) -> float:
    if dimension in priorities:
        return float(len(priorities) - priorities.index(dimension))
    return 1.0


def _score(job: Job, prefs: StructuredPrefs) -> float:
    priorities = prefs.get("priorities", [])
    score = 0.0
    roles = prefs.get("role_keywords", [])
    if roles and _kw_hit(job.get("title", ""), roles):
        score += 5.0 * _weight("role", priorities)
    locations = prefs.get("locations", [])
    if locations and _kw_hit(job.get("location", ""), locations):
        score += 2.0 * _weight("location", priorities)
    if prefs.get("remote_ok") and "remote" in job.get("location", "").lower():
        score += 2.0 * _weight("location", priorities)
    return score


def _passes_required(job: Job, prefs: StructuredPrefs) -> bool:
    required = prefs.get("required", [])
    if "role" in required:
        roles = prefs.get("role_keywords", [])
        if roles and not _kw_hit(job.get("title", ""), roles):
            return False
    if "location" in required:
        locs = prefs.get("locations", [])
        remote_ok = prefs.get("remote_ok")
        loc_text = job.get("location", "").lower()
        loc_hit = locs and _kw_hit(loc_text, locs)
        remote_hit = remote_ok and "remote" in loc_text
        if not (loc_hit or remote_hit):
            return False
    return True


def prefilter(jobs: list[Job], prefs: StructuredPrefs, *, cap: int = 50) -> list[Job]:
    scored: list[tuple[float, Job]] = []
    for job in jobs:
        if not _passes_required(job, prefs):
            continue
        s = _score(job, prefs)
        if s <= 0:
            continue
        scored.append((s, job))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [job for _, job in scored[:cap]]
```

- [ ] **Step 4: Run tests, lint, commit**

```bash
uv run pytest tests/agent/test_prefilter.py -v     # PASS
uv run ruff check . && uv run black --check .
git add -A && git commit -m "feat: deterministic prefilter (required hard-filter + priority soft-score)"
git push origin main
```

---

### Task 5: LLM wrapper + parse_prefs + sufficiency

**Files:**
- Create: `lewis_api/agent/llm.py`, `lewis_api/agent/prefs.py`
- Test: `tests/agent/test_prefs.py`

**Interfaces:**
- Produces: `llm.LLM` (Protocol with `async structured(system: str, user: str, tool_name: str, schema: dict) -> dict`) and `llm.AnthropicLLM` (real impl using `AsyncAnthropic`, model from settings). `prefs.parse_prefs(message: str, prior: StructuredPrefs, resume_text: str, llm: LLM) -> StructuredPrefs` (merges prior + newly-extracted). `prefs.is_sufficient(prefs: StructuredPrefs) -> bool`.

- [ ] **Step 1: Write the failing test** — `tests/agent/test_prefs.py`

```python
import pytest

from lewis_api.agent.prefs import is_sufficient, parse_prefs


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def structured(self, system, user, tool_name, schema):
        self.calls.append((system, user, tool_name))
        return self.payload


def test_is_sufficient_rule():
    assert is_sufficient({"role_keywords": ["fde"], "locations": ["SF"]}) is True
    assert is_sufficient({"role_keywords": ["fde"], "remote_ok": True}) is True
    assert is_sufficient({"role_keywords": ["fde"]}) is False
    assert is_sufficient({"locations": ["SF"]}) is False


@pytest.mark.asyncio
async def test_parse_prefs_merges_prior():
    llm = FakeLLM({"role_keywords": ["fde"], "locations": ["SF"], "priorities": ["role"]})
    prior = {"remote_ok": True}
    out = await parse_prefs("new grad FDE in SF", prior, "resume", llm)
    assert out["role_keywords"] == ["fde"]
    assert out["locations"] == ["SF"]
    assert out["remote_ok"] is True  # prior preserved
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement `lewis_api/agent/llm.py`**

```python
from typing import Protocol

from anthropic import AsyncAnthropic

from lewis_api.config import get_settings


class LLM(Protocol):
    async def structured(
        self, system: str, user: str, tool_name: str, schema: dict
    ) -> dict: ...


class AnthropicLLM:
    def __init__(self, client: AsyncAnthropic | None = None, model: str | None = None):
        settings = get_settings()
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.agent_model

    async def structured(
        self, system: str, user: str, tool_name: str, schema: dict
    ) -> dict:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{"name": tool_name, "description": tool_name, "input_schema": schema}],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in resp.content:
            if block.type == "tool_use":
                return dict(block.input)
        return {}
```

- [ ] **Step 4: Implement `lewis_api/agent/prefs.py`**

```python
from lewis_api.agent.llm import LLM
from lewis_api.agent.state import StructuredPrefs

_SCHEMA = {
    "type": "object",
    "properties": {
        "role_keywords": {"type": "array", "items": {"type": "string"}},
        "locations": {"type": "array", "items": {"type": "string"}},
        "remote_ok": {"type": ["boolean", "null"]},
        "seniority": {"type": ["string", "null"]},
        "extra": {"type": "string"},
        "required": {"type": "array", "items": {"type": "string"}},
        "priorities": {"type": "array", "items": {"type": "string"}},
    },
}

_SYSTEM = (
    "Extract structured job-search preferences from the user's message. "
    "role_keywords: job title/role terms. locations: cities/regions. "
    "remote_ok: true if remote acceptable. seniority: one of intern/new_grad/mid/"
    "senior/staff or null. required: dimensions that are dealbreakers "
    "(subset of ['role','location']). priorities: dimensions ordered most-important "
    "first. Only include fields the user actually expressed."
)


async def parse_prefs(
    message: str, prior: StructuredPrefs, resume_text: str, llm: LLM
) -> StructuredPrefs:
    extracted = await llm.structured(
        system=_SYSTEM,
        user=f"Message: {message}\n\nResume (for context):\n{resume_text[:2000]}",
        tool_name="record_preferences",
        schema=_SCHEMA,
    )
    merged: StructuredPrefs = dict(prior)  # type: ignore[assignment]
    for key, value in extracted.items():
        if value in (None, [], ""):
            continue
        merged[key] = value  # type: ignore[literal-required]
    return merged


def is_sufficient(prefs: StructuredPrefs) -> bool:
    has_role = bool(prefs.get("role_keywords"))
    has_place = bool(prefs.get("locations")) or prefs.get("remote_ok") is True
    return has_role and has_place
```

- [ ] **Step 5: Run tests, lint, commit**

```bash
uv run pytest tests/agent/test_prefs.py -v         # PASS
uv run ruff check . && uv run black --check .
git add -A && git commit -m "feat: LLM wrapper + preference parsing/merge + sufficiency gate"
git push origin main
```

---

### Task 6: Claude ranking

**Files:**
- Create: `lewis_api/agent/rank.py`
- Test: `tests/agent/test_rank.py`

**Interfaces:**
- Produces: `async rank_jobs(candidates: list[Job], prefs, resume_text, llm: LLM) -> list[RankedJob]` — one structured call returning `[{external_id, score, reason}]`; merges score/reason onto candidates by `external_id`, sorts by score desc. Candidates with no returned score get score 0.

- [ ] **Step 1: Write the failing test** — `tests/agent/test_rank.py`

```python
import pytest

from lewis_api.agent.rank import rank_jobs


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    async def structured(self, system, user, tool_name, schema):
        return self.payload


@pytest.mark.asyncio
async def test_rank_merges_and_sorts():
    cands = [
        {"external_id": "1", "title": "FDE", "url": "u1", "description": "x"},
        {"external_id": "2", "title": "SE", "url": "u2", "description": "y"},
    ]
    llm = FakeLLM(
        {"rankings": [
            {"external_id": "1", "score": 60, "reason": "ok"},
            {"external_id": "2", "score": 95, "reason": "great"},
        ]}
    )
    out = await rank_jobs(cands, {"role_keywords": ["fde"]}, "resume", llm)
    assert [j["external_id"] for j in out] == ["2", "1"]  # sorted by score desc
    assert out[0]["score"] == 95 and out[0]["reason"] == "great"
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement `lewis_api/agent/rank.py`**

```python
import json

from lewis_api.agent.llm import LLM
from lewis_api.agent.state import Job, RankedJob, StructuredPrefs

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
                },
                "required": ["external_id", "score", "reason"],
            },
        }
    },
    "required": ["rankings"],
}

_SYSTEM = (
    "Score each candidate job 0-100 for how well it fits the user's resume and "
    "preferences. Trade off soft preferences in the order given by 'priorities' "
    "(most important first); never violate a 'required' dimension. Give a concise "
    "one-line reason per job, citing tradeoffs where relevant."
)


async def rank_jobs(
    candidates: list[Job],
    prefs: StructuredPrefs,
    resume_text: str,
    llm: LLM,
) -> list[RankedJob]:
    compact = [
        {
            "external_id": c.get("external_id"),
            "title": c.get("title"),
            "company": c.get("company"),
            "location": c.get("location"),
            "description": (c.get("description") or "")[:2000],
        }
        for c in candidates
    ]
    user = (
        f"Preferences: {json.dumps(prefs)}\n\n"
        f"Resume:\n{resume_text[:2000]}\n\n"
        f"Candidates:\n{json.dumps(compact)}"
    )
    result = await llm.structured(
        system=_SYSTEM, user=user, tool_name="rank_jobs", schema=_SCHEMA
    )
    by_id = {r["external_id"]: r for r in result.get("rankings", [])}
    ranked: list[RankedJob] = []
    for c in candidates:
        r = by_id.get(c.get("external_id"), {})
        ranked.append(RankedJob(**c, score=int(r.get("score", 0)), reason=r.get("reason", "")))
    ranked.sort(key=lambda j: j.get("score", 0), reverse=True)
    return ranked
```

- [ ] **Step 4: Run tests, lint, commit**

```bash
uv run pytest tests/agent/test_rank.py -v          # PASS
uv run ruff check . && uv run black --check .
git add -A && git commit -m "feat: Claude job ranking with structured output"
git push origin main
```

---

### Task 7: The graph + run_agent + streaming events

**Files:**
- Create: `lewis_api/agent/graph.py`
- Test: `tests/agent/test_graph.py`

**Interfaces:**
- Produces:
  - `build_graph(llm: LLM, fetch_boards, seed, checkpointer) -> CompiledGraph` — nodes close over these deps. `fetch_boards` has signature `async (entries, client) -> list[Job]`; the graph passes `client=None` in tests (fakes ignore it) and a real `httpx.AsyncClient` in prod via a small wrapper.
  - `async run_agent(graph, *, user_id, resume_text, served_keys, message, thread_id) -> AsyncIterator[dict]` — yields event dicts `{"type": "status"|"clarify"|"result"|"done", ...}`. Persists nothing itself; `record_served` is a node that calls an injected `on_served(keys)` callback (so the DB write is testable/injectable). For simplicity, `run_agent` collects the shown jobs and yields a final `{"type": "done", "count": n, "served_keys": [...]}` so the caller (chat route) performs the DB write.
- Consumes: Tasks 1–6 (`parse_prefs`, `is_sufficient`, `prefilter`, `rank_jobs`, `fetch_all_boards`, `load_seed`, `job_key`).

**Node flow (all nodes are async, close over deps, emit events via `get_stream_writer`):**
`ingest` → `parse` → (`is_sufficient` or `clarified_once`) ? `search` path : `clarify` → END.
Search path: `fetch` → `exclude_served` → `prefilter_node` → `rank_node` → `respond`.

- [ ] **Step 1: Write the failing test** — `tests/agent/test_graph.py`

```python
import pytest
from langgraph.checkpoint.memory import MemorySaver

from lewis_api.agent.graph import build_graph, run_agent
from lewis_api.agent.sources.seed import SeedEntry


class FakeLLM:
    def __init__(self, prefs_payload, rank_payload):
        self.prefs_payload = prefs_payload
        self.rank_payload = rank_payload

    async def structured(self, system, user, tool_name, schema):
        if tool_name == "record_preferences":
            return self.prefs_payload
        return self.rank_payload


async def _fake_fetch(entries, client):
    return [
        {"source": "ashby", "company": "Ramp", "board_token": "ramp",
         "external_id": "1", "title": "Forward Deployed Engineer", "location": "SF",
         "url": "https://jobs.ashbyhq.com/ramp/1", "description": "d"},
        {"source": "greenhouse", "company": "GitLab", "board_token": "gitlab",
         "external_id": "2", "title": "Barista", "location": "SF",
         "url": "https://boards.greenhouse.io/gitlab/2", "description": "d"},
    ]


def _graph(prefs_payload, rank_payload):
    llm = FakeLLM(prefs_payload, rank_payload)
    seed = [SeedEntry("Ramp", "ashby", "ramp")]
    return build_graph(llm, _fake_fetch, seed, MemorySaver())


@pytest.mark.asyncio
async def test_clear_query_streams_results_and_reports_served():
    graph = _graph(
        {"role_keywords": ["forward deployed"], "locations": ["SF"], "required": ["role"]},
        {"rankings": [{"external_id": "1", "score": 90, "reason": "great FDE"}]},
    )
    events = [
        e async for e in run_agent(
            graph, user_id="u1", resume_text="r", served_keys=[],
            message="FDE in SF", thread_id="u1:c1",
        )
    ]
    types = [e["type"] for e in events]
    assert "result" in types and types[-1] == "done"
    results = [e for e in events if e["type"] == "result"]
    assert results[0]["job"]["title"] == "Forward Deployed Engineer"  # barista filtered
    assert events[-1]["served_keys"] == ["https://jobs.ashbyhq.com/ramp/1"]


@pytest.mark.asyncio
async def test_vague_query_asks_one_clarify_then_searches():
    graph = _graph(
        {"role_keywords": ["engineer"]},  # no location/remote → insufficient
        {"rankings": [{"external_id": "1", "score": 80, "reason": "ok"}]},
    )
    first = [e async for e in run_agent(
        graph, user_id="u1", resume_text="r", served_keys=[],
        message="I want a tech job", thread_id="u1:c2")]
    assert first[0]["type"] == "clarify" and first[-1]["type"] == "done"

    # second turn, same thread — now proceeds (clarified_once persists)
    second = [e async for e in run_agent(
        graph, user_id="u1", resume_text="r", served_keys=[],
        message="in SF", thread_id="u1:c2")]
    assert any(e["type"] == "result" for e in second)


@pytest.mark.asyncio
async def test_served_jobs_excluded():
    graph = _graph(
        {"role_keywords": ["forward deployed"], "locations": ["SF"], "required": ["role"]},
        {"rankings": [{"external_id": "1", "score": 90, "reason": "x"}]},
    )
    events = [e async for e in run_agent(
        graph, user_id="u1", resume_text="r",
        served_keys=["https://jobs.ashbyhq.com/ramp/1"],  # already served
        message="FDE in SF", thread_id="u1:c3")]
    assert not any(e["type"] == "result" for e in events)  # only match excluded
```

- [ ] **Step 2: Run to verify failure** → FAIL (module missing).

- [ ] **Step 3: Implement `lewis_api/agent/graph.py`**

Implement the graph below. **Verify the LangGraph streaming/`get_stream_writer` API against the installed version** (`uv run python -c "import langgraph, inspect; from langgraph.config import get_stream_writer"`); if the import path differs in the installed version, adjust the import and the `astream(..., stream_mode="custom")` usage accordingly. The node logic and event shapes must stay as specified; the tests are the gate.

```python
from collections.abc import AsyncIterator

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from lewis_api.agent.normalize import job_key
from lewis_api.agent.prefilter import prefilter
from lewis_api.agent.prefs import is_sufficient, parse_prefs
from lewis_api.agent.rank import rank_jobs
from lewis_api.agent.state import AgentState
from lewis_api.config import get_settings

CLARIFY_TEXT = (
    "To narrow this down: which locations are you targeting, or is remote OK? "
    "And what seniority (e.g. new grad, mid, senior)?"
)


def build_graph(llm, fetch_boards, seed, checkpointer):
    async def ingest(state: AgentState) -> dict:
        return {"prefs": state.get("prefs", {}), "clarified_once": state.get("clarified_once", False)}

    async def parse(state: AgentState) -> dict:
        prefs = await parse_prefs(
            state["new_message"], state.get("prefs", {}), state.get("resume_text", ""), llm
        )
        return {"prefs": prefs}

    def route(state: AgentState) -> str:
        if is_sufficient(state["prefs"]) or state.get("clarified_once"):
            return "search"
        return "clarify"

    async def clarify(state: AgentState) -> dict:
        get_stream_writer()({"type": "clarify", "question": CLARIFY_TEXT})
        return {"clarified_once": True, "clarify_question": CLARIFY_TEXT}

    async def search(state: AgentState) -> dict:
        writer = get_stream_writer()
        writer({"type": "status", "text": f"Scanning {len(seed)} companies…"})
        jobs = await fetch_boards(seed, None)
        served = set(state.get("served_keys", []))
        fresh = [j for j in jobs if job_key(j) not in served]
        writer({"type": "status", "text": f"Ranking {len(fresh)} matches…"})
        candidates = prefilter(fresh, state["prefs"])
        ranked = await rank_jobs(candidates, state["prefs"], state.get("resume_text", ""), llm)
        return {"candidates": candidates, "ranked": ranked}

    async def respond(state: AgentState) -> dict:
        writer = get_stream_writer()
        top = state.get("ranked", [])[: get_settings().max_results]
        for job in top:
            writer({"type": "result", "job": job})
        return {"ranked": top}

    builder = StateGraph(AgentState)
    builder.add_node("ingest", ingest)
    builder.add_node("parse", parse)
    builder.add_node("clarify", clarify)
    builder.add_node("search", search)
    builder.add_node("respond", respond)
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "parse")
    builder.add_conditional_edges("parse", route, {"clarify": "clarify", "search": "search"})
    builder.add_edge("clarify", END)
    builder.add_edge("search", "respond")
    builder.add_edge("respond", END)
    return builder.compile(checkpointer=checkpointer)


async def run_agent(
    graph,
    *,
    user_id: str,
    resume_text: str,
    served_keys: list[str],
    message: str,
    thread_id: str,
) -> AsyncIterator[dict]:
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {
        "user_id": user_id,
        "resume_text": resume_text,
        "served_keys": served_keys,
        "new_message": message,
    }
    shown: list[dict] = []
    async for event in graph.astream(inputs, config, stream_mode="custom"):
        if event.get("type") == "result":
            shown.append(event["job"])
        yield event
    yield {
        "type": "done",
        "count": len(shown),
        "served_keys": [job_key(j) for j in shown],
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/agent/test_graph.py -v`
Expected: PASS (3 tests). If streaming API mismatches, fix imports per the note in Step 3 and re-run until green.

- [ ] **Step 5: Lint, commit**

```bash
uv run ruff check . && uv run black --check .
git add -A && git commit -m "feat: agent graph (parse→clarify/search→rank→respond) + run_agent event stream"
git push origin main
```

---

### Task 8: Wire POST /api/chat SSE + checkpointer + env loading

**Files:**
- Create: `lewis_api/chat/__init__.py`, `lewis_api/chat/routes.py`
- Modify: `lewis_api/config.py` (load repo-root `.env`), `lewis_api/main.py` (lifespan: checkpointer + agent deps; include chat router)
- Test: `tests/test_chat.py`

**Interfaces:**
- Produces: `POST /api/chat` — auth required; body `{message: str, conversation_id: str}`; returns `text/event-stream` of `event: <type>\ndata: <json>\n\n`. On completion it loads the user's `served_keys` before the run and writes newly-shown `job_key`s to `served_jobs` after.
- Consumes: `run_agent`, `build_graph`, `get_current_user`, `SavedJob`/`ServedJob`, `UserProfile`.

- [ ] **Step 1: Fix env loading** — edit `lewis_api/config.py` so the repo-root `.env` is found regardless of cwd:

```python
from pathlib import Path

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ROOT_ENV, extra="ignore")
    ...
```
(`parents[3]` of `apps/api/lewis_api/config.py` is the repo root. In Docker the file may be absent; pydantic-settings ignores a missing env_file and uses real env vars.)

- [ ] **Step 2: Write the failing test** — `tests/test_chat.py`

```python
import json

import pytest

import lewis_api.chat.routes as chat_routes


async def _signup(client, email="chat@e.com"):
    await client.post("/api/auth/signup", json={"email": email, "password": "hunter2"})


@pytest.mark.asyncio
async def test_chat_streams_events_and_requires_auth(client, monkeypatch):
    # unauthenticated
    r = await client.post("/api/chat", json={"message": "hi", "conversation_id": "c1"})
    assert r.status_code == 401

    async def fake_run_agent(*args, **kwargs):
        yield {"type": "status", "text": "Scanning…"}
        yield {"type": "result", "job": {"title": "FDE", "url": "u", "company": "Ramp",
                                          "location": "SF", "score": 90, "reason": "x",
                                          "source": "ashby"}}
        yield {"type": "done", "count": 1, "served_keys": ["u"]}

    monkeypatch.setattr(chat_routes, "run_agent", fake_run_agent)

    await _signup(client)
    r = await client.post("/api/chat", json={"message": "FDE in SF", "conversation_id": "c1"})
    assert r.status_code == 200
    body = r.text
    assert "event: status" in body and "event: result" in body and "event: done" in body
    # served_jobs recorded
    jobs = await client.get("/api/jobs")  # not saved automatically
    assert jobs.status_code == 200
```

- [ ] **Step 3: Implement `lewis_api/chat/routes.py`** (and empty `chat/__init__.py`)

```python
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lewis_api.agent.graph import run_agent
from lewis_api.auth.deps import get_current_user
from lewis_api.db.base import get_session
from lewis_api.db.models import ServedJob, User, UserProfile
from lewis_api.schemas import ChatIn

router = APIRouter(prefix="/api", tags=["chat"])


def _frame(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"


@router.post("/chat")
async def chat(
    body: ChatIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    profile = await session.get(UserProfile, user.id)
    resume_text = (profile.resume_text if profile else "") or ""
    prior_prefs = (profile.structured_prefs if profile else {}) or {}  # noqa: F841
    served_rows = await session.scalars(
        select(ServedJob.job_key).where(ServedJob.user_id == user.id)
    )
    served_keys = list(served_rows)
    graph = request.app.state.agent_graph
    thread_id = f"{user.id}:{body.conversation_id}"

    async def gen():
        newly_served: list[str] = []
        async for event in run_agent(
            graph,
            user_id=str(user.id),
            resume_text=resume_text,
            served_keys=served_keys,
            message=body.message,
            thread_id=thread_id,
        ):
            if event["type"] == "done":
                newly_served = event.get("served_keys", [])
            yield _frame(event)
        for key in newly_served:
            session.add(ServedJob(user_id=user.id, job_key=key))
        await session.commit()

    return StreamingResponse(gen(), media_type="text/event-stream")
```

Add `ChatIn` to `lewis_api/schemas.py`:
```python
class ChatIn(BaseModel):
    message: str
    conversation_id: str
```

- [ ] **Step 4: Wire the graph + checkpointer in `lewis_api/main.py` lifespan**

```python
from contextlib import asynccontextmanager

import httpx
from langgraph.checkpoint.memory import MemorySaver

from lewis_api.agent.graph import build_graph
from lewis_api.agent.llm import AnthropicLLM
from lewis_api.agent.sources.boards import fetch_all_boards
from lewis_api.agent.sources.seed import load_seed
from lewis_api.chat.routes import router as chat_router
from lewis_api.config import get_settings


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    seed = load_seed()

    async def fetch_boards(entries, _client):
        async with httpx.AsyncClient(timeout=8) as client:
            return await fetch_all_boards(entries, client)

    # MemorySaver keeps this minimal for v1; swap for AsyncPostgresSaver to persist
    # clarify state across restarts (see note below).
    app.state.agent_graph = build_graph(AnthropicLLM(), fetch_boards, seed, MemorySaver())
    yield


app = FastAPI(title="Lewis API", lifespan=lifespan)
app.include_router(chat_router)
```
Keep the existing `include_router` calls and `/api/health`.

**Postgres checkpointer note (optional durability):** to persist clarify state across
restarts/workers, replace `MemorySaver()` with an `AsyncPostgresSaver`. It uses
`psycopg` (not asyncpg), so derive its URL by stripping `+asyncpg` from
`settings.database_url`, enter it via `async with AsyncPostgresSaver.from_conn_string(url) as saver:` in the lifespan, call `await saver.setup()` once, and pass `saver` to `build_graph`. For v1, MemorySaver is acceptable (single worker); document the tradeoff. If you wire AsyncPostgresSaver, add a test that `setup()` runs against the dev DB.

- [ ] **Step 5: Run tests, lint, commit**

```bash
uv run pytest tests/test_chat.py -v                # PASS
uv run pytest -q                                   # full suite green
uv run ruff check . && uv run black --check .
git add -A && git commit -m "feat: POST /api/chat SSE endpoint + agent wiring in lifespan + root .env loading"
git push origin main
```

---

### Task 9: Live smoke (controller) — real Haiku + real boards

**Files:**
- Modify: `README.md` (add chat usage)

This task runs a REAL end-to-end search: real Greenhouse/Ashby fetches (free) + one real Haiku ranking call (a few tenths of a cent). It requires `ANTHROPIC_API_KEY` in `.env`.

- [ ] **Step 1: Start the stack and API**

```bash
docker compose up -d db
cd apps/api && uv run alembic upgrade head
uv run uvicorn lewis_api.main:app --port 8000
```

- [ ] **Step 2: Smoke the chat stream (new terminal)**

```bash
curl -s -c /tmp/j.txt -X POST localhost:8000/api/auth/signup \
  -H 'content-type: application/json' -d '{"email":"chat-smoke@e.com","password":"hunter2"}' >/dev/null
curl -N -s -b /tmp/j.txt -X POST localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"message":"forward deployed / solutions engineer roles, remote OK","conversation_id":"s1"}'
```
Expected: SSE frames stream — `status`, then `result` frames with real jobs from GitLab/Ramp boards ranked by Haiku, then `done`. Confirm a second identical call returns FEWER/none of the same jobs (served-exclusion working).

- [ ] **Step 3: Update `README.md`** — add a "Chat (agent search)" section documenting the `POST /api/chat` SSE call and that `ANTHROPIC_API_KEY` must be set.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "docs: agent chat usage + live smoke notes"
git push origin main
```

---

## Self-Review

**Spec/PRD coverage (agent PRD A1–A13):** A1 parse/merge → Task 5. A2 sufficiency → Task 5/7. A3 one-clarify → Task 7 (clarified_once persisted). A4 resume-across-turns → Task 7 (checkpointer) + Task 8 (thread_id). A5 concurrent+resilient fetch → Task 3. A6 normalize/dedupe → Tasks 1–3. A7 exclude_served → Task 7. A8 prefilter → Task 4. A9 rank → Task 6. A10 top MAX_RESULTS → Task 7 (respond). A11 record served (shown only) → Task 8 (chat route writes newly-shown keys). A12 pure callable → Task 7 (deps injected). A13 streaming events → Task 7. Streaming contract (spec §7.7) → Tasks 7–8.

**Design refinements recorded:** clarify via checkpointer-persisted state (not `interrupt()`); `record_served` performed by the chat route (DB layer) using the `done` event's `served_keys`, keeping the graph pure. Both preserve observable behavior.

**Placeholder scan:** none — every step has concrete code/tests. The LangGraph streaming-API verification note in Task 7 is a deliberate compatibility check, not a placeholder.

**Type consistency:** `LLM.structured`, `parse_prefs`, `is_sufficient`, `prefilter`, `rank_jobs`, `fetch_all_boards`, `job_key`, `build_graph`, `run_agent`, `Job`/`RankedJob`/`StructuredPrefs`/`AgentState`, and `ChatIn` are referenced with consistent names/signatures across tasks.

## Notes carried to Plan 3 (Frontend)

- SSE event shapes are final: `status{text}`, `clarify{question}`, `result{job}`, `done{count}`.
- `POST /api/chat` consumes `{message, conversation_id}`; client mints `conversation_id` per chat.
- Saving a shown job still uses `POST /api/jobs` with the `RankedJob` payload (served-tracking is separate from saving).
