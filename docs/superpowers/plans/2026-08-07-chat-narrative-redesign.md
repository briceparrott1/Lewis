# Chat UX Redesign — Loading Feedback & Narrative Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two static "Scanning…"/"Ranking…" status lines and flat job-card list in the chat UI with (a) research-backed loading feedback that mixes real backend phase updates with occasional playful filler text, and (b) an LLM-written narrative paragraph (addressing the user by name) followed by a compact, still-actionable job list.

**Architecture:** Backend gains a `narrate_results()` step in the LangGraph `respond` node (new `LLM.complete()` free-text method, new `narrative` SSE event) and ~5 granular real `status` events across existing nodes. Frontend gains a `useStatusTicker` hook that layers filler phrases onto real status text with research-backed timing, and a rewritten `Chat.tsx` that renders the narrative + a new compact job row instead of full `JobCard`s.

**Tech Stack:** FastAPI + LangGraph + `AsyncAnthropic` (backend), React + TypeScript + Tailwind v4 + Vitest (frontend). No new dependencies on either side.

## Global Constraints

- Backend: Python 3.12, format with `black` (88 cols), lint clean via `ruff check .`, type hints on public functions. Before each backend commit: `cd apps/api && uv run pytest -q && uv run ruff check . && uv run black --check .`.
- Frontend: TypeScript, Tailwind v4 utility classes only — no new CSS files, no new npm dependencies (the spinner uses Tailwind's built-in `animate-bounce`). Before each frontend commit: `cd apps/web && pnpm test && pnpm typecheck`.
- No new dependencies (Python or JS) anywhere in this plan.
- Every LLM-dependent unit is tested with a small hand-written duck-typed fake class (matching the existing pattern in `test_rank.py`/`test_prefs.py`/`test_graph.py`) — no mocking library.
- Existing SSE event shapes (`status`, `clarify`, `result`, `done`) are unchanged; only the new `narrative` event is added.
- Each task ends with its own commit.

---

### Task 1: `LLM.complete()` — free-text completion method

**Files:**
- Modify: `apps/api/lewis_api/agent/llm.py`
- Test: `apps/api/tests/agent/test_llm.py` (new file)

**Interfaces:**
- Produces: `LLM.complete(system: str, user: str) -> str` (async), on the `LLM` Protocol and implemented by `AnthropicLLM.complete`. Task 2 depends on this.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/agent/test_llm.py`:

```python
import pytest

from lewis_api.agent.llm import AnthropicLLM


class _Resp:
    def __init__(self, content):
        self.content = content


class _TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeMessages:
    def __init__(self, content):
        self._content = content

    async def create(self, **kwargs):
        return _Resp(self._content)


class _FakeClient:
    def __init__(self, content):
        self.messages = _FakeMessages(content)


@pytest.mark.asyncio
async def test_complete_returns_text_block_content():
    llm = AnthropicLLM(client=_FakeClient([_TextBlock("hello there")]), model="fake-model")
    out = await llm.complete(system="s", user="u")
    assert out == "hello there"


@pytest.mark.asyncio
async def test_complete_returns_empty_string_when_no_text_block():
    llm = AnthropicLLM(client=_FakeClient([]), model="fake-model")
    out = await llm.complete(system="s", user="u")
    assert out == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/agent/test_llm.py -v`
Expected: FAIL — `AttributeError: 'AnthropicLLM' object has no attribute 'complete'`

- [ ] **Step 3: Implement `complete()`**

In `apps/api/lewis_api/agent/llm.py`, add `complete` to the `LLM` Protocol (after the existing `structured` method):

```python
class LLM(Protocol):
    async def structured(
        self, system: str, user: str, tool_name: str, schema: dict
    ) -> dict: ...

    async def complete(self, system: str, user: str) -> str: ...
```

And add the method to `AnthropicLLM` (after `structured`):

```python
    async def complete(self, system: str, user: str) -> str:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        for block in resp.content:
            if block.type == "text":
                return block.text
        return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_llm.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lint, format, commit**

```bash
cd apps/api && uv run ruff check . && uv run black --check .
git add apps/api/lewis_api/agent/llm.py apps/api/tests/agent/test_llm.py
git commit -m "feat(api): add LLM.complete() free-text method"
```

---

### Task 2: `narrate_results()` — narrative generation

**Files:**
- Create: `apps/api/lewis_api/agent/narrate.py`
- Test: `apps/api/tests/agent/test_narrate.py` (new file)

**Interfaces:**
- Consumes: `LLM.complete(system: str, user: str) -> str` (Task 1).
- Produces: `narrate_results(ranked: list[RankedJob], prefs: StructuredPrefs, resume_text: str, user_name: str | None, llm: LLM) -> str`. Task 3 depends on this.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/agent/test_narrate.py`:

```python
import pytest

from lewis_api.agent.narrate import narrate_results

RANKED = [
    {
        "external_id": "1",
        "title": "FDE",
        "company": "Ramp",
        "location": "SF",
        "score": 92,
        "reason": "Matches your backend + customer-facing experience",
    },
    {
        "external_id": "2",
        "title": "Support Engineer",
        "company": "GitLab",
        "location": "Remote",
        "score": 61,
        "reason": "Lower seniority but remote-friendly",
    },
]


class FakeLLM:
    def __init__(self, text=None, raise_exc=None):
        self.text = text
        self.raise_exc = raise_exc
        self.calls = []

    async def complete(self, system, user):
        self.calls.append((system, user))
        if self.raise_exc:
            raise self.raise_exc
        return self.text


@pytest.mark.asyncio
async def test_narrate_calls_llm_with_context():
    llm = FakeLLM(text="Hey Brice, I found 2 roles for you...")
    out = await narrate_results(
        RANKED, {"role_keywords": ["fde"]}, "resume text", "Brice", llm
    )
    assert out == "Hey Brice, I found 2 roles for you..."
    assert len(llm.calls) == 1
    _, user = llm.calls[0]
    assert "Brice" in user
    assert "FDE" in user
    assert "Ramp" in user


@pytest.mark.asyncio
async def test_narrate_skips_llm_call_when_no_results():
    llm = FakeLLM(text="should not be used")
    out = await narrate_results([], {"role_keywords": ["fde"]}, "resume text", "Brice", llm)
    assert out == (
        "I didn't find any roles matching that this time — try broadening your "
        "criteria (location, seniority, or role type) and I'll take another look."
    )
    assert llm.calls == []


@pytest.mark.asyncio
async def test_narrate_falls_back_on_llm_error():
    llm = FakeLLM(raise_exc=RuntimeError("boom"))
    out = await narrate_results(
        RANKED, {"role_keywords": ["fde"]}, "resume text", "Brice", llm
    )
    assert out == "I found 2 jobs matching your search."


@pytest.mark.asyncio
async def test_narrate_uses_generic_greeting_when_no_name():
    llm = FakeLLM(text="Hi there, found some roles.")
    out = await narrate_results(RANKED, {}, "resume", None, llm)
    assert out == "Hi there, found some roles."
    _, user = llm.calls[0]
    assert "there" in user
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/agent/test_narrate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lewis_api.agent.narrate'`

- [ ] **Step 3: Implement `narrate.py`**

Create `apps/api/lewis_api/agent/narrate.py`:

```python
import json

from lewis_api.agent.llm import LLM
from lewis_api.agent.state import RankedJob, StructuredPrefs

_SYSTEM = (
    "You are a friendly job-search assistant writing a short summary of search "
    "results directly to the user in a chat. Address them by name. Say how many "
    "jobs you found. Call out the top-ranked result by title and company and "
    "explain briefly why it fits, tying back to their resume or preferences. If "
    "another result is a bit of a stretch from what they asked for, mention it "
    "and say why it might still be worth a look. 2-4 sentences, conversational, "
    "no bullet points, no markdown."
)

_NO_RESULTS = (
    "I didn't find any roles matching that this time — try broadening your "
    "criteria (location, seniority, or role type) and I'll take another look."
)


async def narrate_results(
    ranked: list[RankedJob],
    prefs: StructuredPrefs,
    resume_text: str,
    user_name: str | None,
    llm: LLM,
) -> str:
    if not ranked:
        return _NO_RESULTS
    compact = [
        {
            "title": j.get("title"),
            "company": j.get("company"),
            "location": j.get("location"),
            "score": j.get("score"),
            "reason": j.get("reason"),
        }
        for j in ranked
    ]
    user = (
        f"User's name: {user_name or 'there'}\n\n"
        f"Preferences: {json.dumps(prefs)}\n\n"
        f"Ranked results, best first:\n{json.dumps(compact)}"
    )
    try:
        return await llm.complete(system=_SYSTEM, user=user)
    except Exception:
        n = len(ranked)
        return f"I found {n} job{'s' if n != 1 else ''} matching your search."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_narrate.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Lint, format, commit**

```bash
cd apps/api && uv run ruff check . && uv run black --check .
git add apps/api/lewis_api/agent/narrate.py apps/api/tests/agent/test_narrate.py
git commit -m "feat(api): add narrate_results() for LLM-written result summaries"
```

---

### Task 3: Graph wiring — granular status events + narrative event + `user_name` state

**Files:**
- Modify: `apps/api/lewis_api/agent/state.py`
- Modify: `apps/api/lewis_api/agent/graph.py`
- Modify: `apps/api/tests/agent/test_graph.py`

**Interfaces:**
- Consumes: `narrate_results(...)` (Task 2).
- Produces: `run_agent(..., user_name: str | None = None)` — Task 5 depends on this new kwarg. `AgentState.user_name: str | None`.
- New SSE event: `{"type": "narrative", "text": str}`, emitted once per turn from the `respond` node, before `result` events.

- [ ] **Step 1: Update `test_graph.py` to reflect the new event shapes**

Replace the full contents of `apps/api/tests/agent/test_graph.py`:

```python
import pytest
from langgraph.checkpoint.memory import MemorySaver

from lewis_api.agent.graph import build_graph, run_agent
from lewis_api.agent.sources.seed import SeedEntry


class FakeLLM:
    def __init__(self, prefs_payload, rank_payload, narrative_text="Here's what I found."):
        self.prefs_payload = prefs_payload
        self.rank_payload = rank_payload
        self.narrative_text = narrative_text

    async def structured(self, system, user, tool_name, schema):
        if tool_name == "record_preferences":
            return self.prefs_payload
        return self.rank_payload

    async def complete(self, system, user):
        return self.narrative_text


async def _fake_fetch(entries, client):
    return [
        {
            "source": "ashby",
            "company": "Ramp",
            "board_token": "ramp",
            "external_id": "1",
            "title": "Forward Deployed Engineer",
            "location": "SF",
            "url": "https://jobs.ashbyhq.com/ramp/1",
            "description": "d",
        },
        {
            "source": "greenhouse",
            "company": "GitLab",
            "board_token": "gitlab",
            "external_id": "2",
            "title": "Barista",
            "location": "SF",
            "url": "https://boards.greenhouse.io/gitlab/2",
            "description": "d",
        },
    ]


def _graph(prefs_payload, rank_payload):
    llm = FakeLLM(prefs_payload, rank_payload)
    seed = [SeedEntry("Ramp", "ashby", "ramp")]
    return build_graph(llm, _fake_fetch, seed, MemorySaver())


@pytest.mark.asyncio
async def test_clear_query_streams_results_and_reports_served():
    graph = _graph(
        {
            "role_keywords": ["forward deployed"],
            "locations": ["SF"],
            "required": ["role"],
        },
        {"rankings": [{"external_id": "1", "score": 90, "reason": "great FDE"}]},
    )
    events = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            served_keys=[],
            message="FDE in SF",
            thread_id="u1:c1",
            user_name="Brice",
        )
    ]
    types = [e["type"] for e in events]
    # parse + scan + filter + rank + writing-up = 5 real status phases
    assert types.count("status") == 5
    assert "narrative" in types and "result" in types and types[-1] == "done"
    assert types.index("narrative") < types.index("result")
    results = [e for e in events if e["type"] == "result"]
    assert results[0]["job"]["title"] == "Forward Deployed Engineer"  # barista filtered
    assert events[-1]["served_keys"] == ["https://jobs.ashbyhq.com/ramp/1"]


@pytest.mark.asyncio
async def test_vague_query_asks_one_clarify_then_searches():
    graph = _graph(
        {"role_keywords": ["engineer"]},  # no location/remote → insufficient
        {"rankings": [{"external_id": "1", "score": 80, "reason": "ok"}]},
    )
    first = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            served_keys=[],
            message="I want a tech job",
            thread_id="u1:c2",
        )
    ]
    types_first = [e["type"] for e in first]
    assert first[0]["type"] == "status"  # "Reading your resume..." comes first now
    assert "clarify" in types_first and types_first[-1] == "done"

    # second turn, same thread — now proceeds (clarified_once persists)
    second = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            served_keys=[],
            message="in SF",
            thread_id="u1:c2",
        )
    ]
    assert any(e["type"] == "result" for e in second)
    assert any(e["type"] == "narrative" for e in second)


@pytest.mark.asyncio
async def test_served_jobs_excluded():
    graph = _graph(
        {
            "role_keywords": ["forward deployed"],
            "locations": ["SF"],
            "required": ["role"],
        },
        {"rankings": [{"external_id": "1", "score": 90, "reason": "x"}]},
    )
    events = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            served_keys=["https://jobs.ashbyhq.com/ramp/1"],  # already served
            message="FDE in SF",
            thread_id="u1:c3",
        )
    ]
    assert not any(e["type"] == "result" for e in events)  # only match excluded
    narrative_events = [e for e in events if e["type"] == "narrative"]
    assert len(narrative_events) == 1
    assert "didn't find any roles" in narrative_events[0]["text"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/agent/test_graph.py -v`
Expected: FAIL — `TypeError: run_agent() got an unexpected keyword argument 'user_name'` (and `FakeLLM` object has no attribute `complete` once that's fixed) — confirms the graph doesn't support the new behavior yet.

- [ ] **Step 3: Update `state.py`**

In `apps/api/lewis_api/agent/state.py`, add `user_name` to `AgentState` (after `user_id`):

```python
class AgentState(TypedDict, total=False):
    user_id: str
    user_name: str | None
    resume_text: str
    prefs: StructuredPrefs
    clarified_once: bool
    served_keys: list[str]
    new_message: str
    candidates: list[Job]
    ranked: list[RankedJob]
    clarify_question: str | None
```

- [ ] **Step 4: Update `graph.py`**

Replace the full contents of `apps/api/lewis_api/agent/graph.py`:

```python
from collections.abc import AsyncIterator

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from lewis_api.agent.narrate import narrate_results
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
        return {
            "prefs": state.get("prefs", {}),
            "clarified_once": state.get("clarified_once", False),
        }

    async def parse(state: AgentState) -> dict:
        get_stream_writer()(
            {"type": "status", "text": "Reading your resume and preferences…"}
        )
        prefs = await parse_prefs(
            state["new_message"],
            state.get("prefs", {}),
            state.get("resume_text", ""),
            llm,
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
        writer(
            {"type": "status", "text": f"Scanning {len(seed)} companies for openings…"}
        )
        jobs = await fetch_boards(seed, None)
        served = set(state.get("served_keys", []))
        fresh = [j for j in jobs if job_key(j) not in served]
        writer({"type": "status", "text": "Filtering to your criteria…"})
        candidates = prefilter(fresh, state["prefs"])
        writer({"type": "status", "text": "Ranking matches against your profile…"})
        ranked = await rank_jobs(
            candidates, state["prefs"], state.get("resume_text", ""), llm
        )
        return {"candidates": candidates, "ranked": ranked}

    async def respond(state: AgentState) -> dict:
        writer = get_stream_writer()
        top = state.get("ranked", [])[: get_settings().max_results]
        writer({"type": "status", "text": "Writing up what I found…"})
        narrative = await narrate_results(
            top,
            state["prefs"],
            state.get("resume_text", ""),
            state.get("user_name"),
            llm,
        )
        writer({"type": "narrative", "text": narrative})
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
    builder.add_conditional_edges(
        "parse", route, {"clarify": "clarify", "search": "search"}
    )
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
    user_name: str | None = None,
) -> AsyncIterator[dict]:
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {
        "user_id": user_id,
        "resume_text": resume_text,
        "served_keys": served_keys,
        "new_message": message,
        "user_name": user_name,
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

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_graph.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the full backend suite (other tests touch this module transitively)**

Run: `cd apps/api && uv run pytest -q`
Expected: PASS — all tests, including `test_chat.py` (its `fake_run_agent` bypasses the real graph so it's unaffected).

- [ ] **Step 7: Lint, format, commit**

```bash
cd apps/api && uv run ruff check . && uv run black --check .
git add apps/api/lewis_api/agent/state.py apps/api/lewis_api/agent/graph.py apps/api/tests/agent/test_graph.py
git commit -m "feat(api): granular status events + narrative event in agent graph"
```

---

### Task 4: `UserProfile.name` — migration, model, schema, endpoint

**Files:**
- Modify: `apps/api/lewis_api/db/models.py`
- Modify: `apps/api/lewis_api/schemas.py`
- Modify: `apps/api/lewis_api/profile/routes.py`
- Create: `apps/api/alembic/versions/<generated>_user_profile_name.py` (via `alembic revision --autogenerate`)
- Modify: `apps/api/tests/test_profile.py`

**Interfaces:**
- Produces: `UserProfile.name: str | None`; `ProfileOut.name: str | None`; `PUT /api/profile/name` (body: `NameIn{name: str}`, returns `ProfileOut`). Task 5 (chat route) and Task 11 (Onboarding UI) depend on this endpoint/field.

- [ ] **Step 1: Write the failing test**

In `apps/api/tests/test_profile.py`, append:

```python
async def test_put_name(client):
    await _signup(client, "name@e.com")
    resp = await client.put("/api/profile/name", json={"name": "Brice"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Brice"
    prof = await client.get("/api/profile")
    assert prof.json()["name"] == "Brice"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_profile.py::test_put_name -v`
Expected: FAIL — 404 (no `/api/profile/name` route) or `KeyError: 'name'` on the `ProfileOut` response.

- [ ] **Step 3: Add the `name` column to the model**

In `apps/api/lewis_api/db/models.py`, modify `UserProfile` (add `name` as the first field after `user_id`):

```python
class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_prefs_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_prefs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
```

- [ ] **Step 4: Generate and verify the Alembic migration**

Run:
```bash
cd apps/api && uv run alembic revision --autogenerate -m "add user_profile name"
```

Open the generated file under `apps/api/alembic/versions/`. Confirm `down_revision` equals the current head revision id (check `apps/api/alembic/versions/` for the migration with no other migration pointing past it — at plan-writing time this was `8c9314cfd944`, but verify against the actual latest file since other work may have added migrations since) and that `upgrade()`/`downgrade()` match:

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user_profiles', sa.Column('name', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('user_profiles', 'name')
```

If autogenerate produced different formatting, edit the file so `upgrade`/`downgrade` match exactly (keep the tool-generated `revision`/`down_revision`/`Create Date` header as-is).

Apply it to the local dev database:
```bash
uv run alembic upgrade head
```

- [ ] **Step 5: Add `name` to the schemas**

In `apps/api/lewis_api/schemas.py`, modify `ProfileOut` and add `NameIn` (after `ProfileOut`, before `PrefsIn`):

```python
class ProfileOut(BaseModel):
    name: str | None
    resume_text: str | None
    raw_prefs_text: str | None
    structured_prefs: dict

    model_config = {"from_attributes": True}


class NameIn(BaseModel):
    name: str
```

- [ ] **Step 6: Add the `PUT /api/profile/name` endpoint**

In `apps/api/lewis_api/profile/routes.py`, update the import line and add the new endpoint (after `put_prefs`):

```python
from lewis_api.schemas import NameIn, PrefsIn, ProfileOut
```

```python
@router.put("/name", response_model=ProfileOut)
async def put_name(
    body: NameIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserProfile:
    profile = await _get_or_create(session, user.id)
    profile.name = body.name
    await session.commit()
    return profile
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/test_profile.py -v`
Expected: PASS (all tests in this file, including `test_put_name`)

Run: `cd apps/api && uv run pytest -q`
Expected: PASS — full suite (the `ProfileOut` shape change is backward-compatible since `name` is nullable and every existing test that reads a profile response doesn't assert against a fixed key set).

- [ ] **Step 8: Lint, format, commit**

```bash
cd apps/api && uv run ruff check . && uv run black --check .
git add apps/api/lewis_api/db/models.py apps/api/lewis_api/schemas.py apps/api/lewis_api/profile/routes.py apps/api/alembic/versions/ apps/api/tests/test_profile.py
git commit -m "feat(api): add UserProfile.name field and PUT /api/profile/name"
```

---

### Task 5: Wire `user_name` through the chat route

**Files:**
- Modify: `apps/api/lewis_api/chat/routes.py`
- Modify: `apps/api/tests/test_chat.py`

**Interfaces:**
- Consumes: `run_agent(..., user_name: str | None = None)` (Task 3), `UserProfile.name` (Task 4).

- [ ] **Step 1: Write the failing test**

In `apps/api/tests/test_chat.py`, append:

```python
async def test_chat_passes_user_name_to_agent(client, monkeypatch):
    await _signup(client, "named@e.com")
    await client.put("/api/profile/name", json={"name": "Brice"})

    captured = {}

    async def fake_run_agent(*args, **kwargs):
        captured.update(kwargs)
        yield {"type": "done", "count": 0, "served_keys": []}

    monkeypatch.setattr(chat_routes, "run_agent", fake_run_agent)
    app.state.agent_graph = object()

    r = await client.post(
        "/api/chat", json={"message": "hi", "conversation_id": "c1"}
    )
    assert r.status_code == 200
    assert captured["user_name"] == "Brice"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_chat.py::test_chat_passes_user_name_to_agent -v`
Expected: FAIL — `KeyError: 'user_name'` (route doesn't pass it yet)

- [ ] **Step 3: Implement**

In `apps/api/lewis_api/chat/routes.py`, modify the `chat` function body — after the existing `prior_prefs` line, add:

```python
    profile = await session.get(UserProfile, user.id)
    resume_text = (profile.resume_text if profile else "") or ""
    prior_prefs = (profile.structured_prefs if profile else {}) or {}  # noqa: F841
    user_name = (profile.name if profile else None) or None
```

And in the `run_agent(...)` call inside `gen()`, add the new kwarg:

```python
        async for event in run_agent(
            graph,
            user_id=str(user_id),
            resume_text=resume_text,
            served_keys=served_keys,
            message=body.message,
            thread_id=thread_id,
            user_name=user_name,
        ):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/test_chat.py -v`
Expected: PASS (all tests in this file)

Run: `cd apps/api && uv run pytest -q`
Expected: PASS — full backend suite.

- [ ] **Step 5: Lint, format, commit**

```bash
cd apps/api && uv run ruff check . && uv run black --check .
git add apps/api/lewis_api/chat/routes.py apps/api/tests/test_chat.py
git commit -m "feat(api): thread user_name from profile into chat agent run"
```

---

### Task 6: Frontend types — `Profile.name` and `narrative` event

**Files:**
- Modify: `apps/web/src/types.ts`

**Interfaces:**
- Produces: `Profile.name: string | null`; `ChatEvent` gains `{ type: "narrative"; text: string }`. Tasks 8, 10, 11 depend on this.

- [ ] **Step 1: Update `types.ts`**

Modify `Profile` and `ChatEvent` in `apps/web/src/types.ts`:

```ts
export interface Profile {
  name: string | null;
  resume_text: string | null;
  raw_prefs_text: string | null;
  structured_prefs: Record<string, unknown>;
}
```

```ts
export type ChatEvent =
  | { type: "status"; text: string }
  | { type: "clarify"; question: string }
  | { type: "narrative"; text: string }
  | { type: "result"; job: RankedJob }
  | { type: "done"; count: number };
```

- [ ] **Step 2: Verify with the typechecker**

Run: `cd apps/web && pnpm typecheck`
Expected: PASS (no consumer of `Profile`/`ChatEvent` breaks yet, since nothing reads `.name` or matches on `"narrative"` until later tasks)

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/types.ts
git commit -m "feat(web): add Profile.name and narrative ChatEvent type"
```

---

### Task 7: `Spinner` component

**Files:**
- Create: `apps/web/src/components/Spinner.tsx`
- Test: `apps/web/src/components/Spinner.test.tsx`

**Interfaces:**
- Produces: `Spinner` component (no props). Task 10 depends on this.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/components/Spinner.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { it, expect } from "vitest";
import { Spinner } from "./Spinner";

it("renders a loading status indicator", () => {
  render(<Spinner />);
  expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && pnpm test -- Spinner.test.tsx`
Expected: FAIL — cannot find module `./Spinner`

- [ ] **Step 3: Implement `Spinner.tsx`**

Create `apps/web/src/components/Spinner.tsx`:

```tsx
export function Spinner() {
  return (
    <span className="inline-flex gap-1" role="status" aria-label="Loading">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400" />
    </span>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && pnpm test -- Spinner.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/Spinner.tsx apps/web/src/components/Spinner.test.tsx
git commit -m "feat(web): add CSS-only Spinner component"
```

---

### Task 8: `useStatusTicker` hook

**Files:**
- Create: `apps/web/src/lib/useStatusTicker.ts`
- Test: `apps/web/src/lib/useStatusTicker.test.tsx`

**Interfaces:**
- Consumes: nothing beyond React.
- Produces: `useStatusTicker(active: boolean, realText: string | null, options?: StatusTickerOptions): string | null`. Task 10 depends on this.

- [ ] **Step 1: Write the failing tests**

Create `apps/web/src/lib/useStatusTicker.test.tsx`:

```tsx
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useStatusTicker } from "./useStatusTicker";

describe("useStatusTicker", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows real status text immediately when it arrives", () => {
    const { result, rerender } = renderHook(
      ({ active, realText }) => useStatusTicker(active, realText),
      { initialProps: { active: true, realText: null as string | null } },
    );
    expect(result.current).toBeNull();
    act(() => {
      rerender({ active: true, realText: "Scanning 40 companies…" });
    });
    expect(result.current).toBe("Scanning 40 companies…");
  });

  it("swaps to a filler phrase after the swap window if no new real text arrives", () => {
    const { result } = renderHook(
      ({ active, realText }) =>
        useStatusTicker(active, realText, { random: () => 0 }),
      { initialProps: { active: true, realText: "Scanning…" as string | null } },
    );
    expect(result.current).toBe("Scanning…");
    act(() => {
      vi.advanceTimersByTime(3100);
    });
    expect(result.current).not.toBe("Scanning…");
    expect(result.current).not.toBeNull();
  });

  it("does not swap to filler within the cooldown after a fresh real event", () => {
    const { result, rerender } = renderHook(
      ({ active, realText }) =>
        useStatusTicker(active, realText, { random: () => 0 }),
      { initialProps: { active: true, realText: "A" as string | null } },
    );
    act(() => {
      vi.advanceTimersByTime(2500);
    });
    act(() => {
      rerender({ active: true, realText: "B" });
    });
    act(() => {
      vi.advanceTimersByTime(900); // well under the 1.75s minimum-visible floor
    });
    expect(result.current).toBe("B");
  });

  it("stops and resets when active becomes false", () => {
    const { result, rerender } = renderHook(
      ({ active, realText }) => useStatusTicker(active, realText),
      { initialProps: { active: true, realText: "Scanning…" as string | null } },
    );
    act(() => {
      rerender({ active: false, realText: "Scanning…" });
    });
    expect(result.current).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && pnpm test -- useStatusTicker.test.tsx`
Expected: FAIL — cannot find module `./useStatusTicker`

- [ ] **Step 3: Implement `useStatusTicker.ts`**

Create `apps/web/src/lib/useStatusTicker.ts`:

```ts
import { useEffect, useRef, useState } from "react";

export interface StatusTickerOptions {
  fillers?: string[];
  minVisibleMs?: number;
  swapMinMs?: number;
  swapMaxMs?: number;
  realCooldownMs?: number;
  random?: () => number;
}

const DEFAULT_FILLERS = [
  "Sifting through job boards…",
  "Reticulating listings…",
  "Cross-referencing your resume…",
  "Weighing the tradeoffs…",
  "Double-checking the fine print…",
  "Consulting the job-search oracle…",
  "Untangling job titles…",
  "Making sure nothing's missed…",
];

const POLL_MS = 250;

// Timing is research-backed, not arbitrary: NN/g response-time thresholds put
// this kind of wait past the 10s "needs active feedback" mark, and Buell &
// Norton's "labor illusion" findings show specific, real activity text reads
// as more trustworthy than a generic spinner — so real status always wins,
// and filler only fills genuine gaps between real updates.
export function useStatusTicker(
  active: boolean,
  realText: string | null,
  options: StatusTickerOptions = {},
): string | null {
  const {
    fillers = DEFAULT_FILLERS,
    minVisibleMs = 1750,
    swapMinMs = 2000,
    swapMaxMs = 3000,
    realCooldownMs = 1000,
    random = Math.random,
  } = options;

  const [displayText, setDisplayText] = useState<string | null>(null);
  const lastChangeAt = useRef(0);
  const lastRealAt = useRef(0);

  useEffect(() => {
    if (!active || realText === null) return;
    setDisplayText(realText);
    const now = Date.now();
    lastChangeAt.current = now;
    lastRealAt.current = now;
  }, [realText, active]);

  useEffect(() => {
    if (!active) {
      setDisplayText(null);
      return;
    }
    const id = setInterval(() => {
      const now = Date.now();
      const sinceChange = now - lastChangeAt.current;
      const sinceReal = now - lastRealAt.current;
      const swapWindow = swapMinMs + random() * (swapMaxMs - swapMinMs);
      if (sinceChange < minVisibleMs) return;
      if (sinceChange < swapWindow) return;
      if (sinceReal < realCooldownMs) return;
      setDisplayText((current) => {
        const pool = fillers.filter((f) => f !== current);
        const next = pool[Math.floor(random() * pool.length)];
        lastChangeAt.current = now;
        return next;
      });
    }, POLL_MS);
    return () => clearInterval(id);
  }, [active, fillers, minVisibleMs, swapMinMs, swapMaxMs, realCooldownMs, random]);

  return displayText;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm test -- useStatusTicker.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/useStatusTicker.ts apps/web/src/lib/useStatusTicker.test.tsx
git commit -m "feat(web): add useStatusTicker hook with research-backed timing"
```

---

### Task 9: `CompactJobRow` component

**Files:**
- Create: `apps/web/src/components/CompactJobRow.tsx`
- Test: `apps/web/src/components/CompactJobRow.test.tsx`

**Interfaces:**
- Produces: `CompactJobRow({ job: RankedJob, onSave: () => void, busy?: boolean })`. Task 10 depends on this.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/components/CompactJobRow.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi } from "vitest";
import { CompactJobRow } from "./CompactJobRow";

it("renders job title/company and fires onSave", async () => {
  const onSave = vi.fn();
  render(
    <CompactJobRow
      onSave={onSave}
      job={{ source: "ashby", company: "Ramp", title: "FDE", location: "SF", url: "https://x" }}
    />,
  );
  expect(screen.getByText("FDE")).toBeInTheDocument();
  expect(screen.getByText(/Ramp/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  expect(onSave).toHaveBeenCalledOnce();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && pnpm test -- CompactJobRow.test.tsx`
Expected: FAIL — cannot find module `./CompactJobRow`

- [ ] **Step 3: Implement `CompactJobRow.tsx`**

Create `apps/web/src/components/CompactJobRow.tsx`:

```tsx
import type { RankedJob } from "../types";

export function CompactJobRow({
  job, onSave, busy,
}: {
  job: RankedJob;
  onSave: () => void;
  busy?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b py-2 text-sm last:border-b-0">
      <div className="min-w-0">
        <a href={job.url} target="_blank" rel="noreferrer"
          className="font-medium text-blue-700 hover:underline">{job.title}</a>
        <p className="truncate text-gray-500">
          {job.company}{job.location ? ` · ${job.location}` : ""}
        </p>
      </div>
      <button onClick={onSave} disabled={busy}
        className="shrink-0 rounded border px-2 py-1 text-xs hover:bg-gray-50">
        Save
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && pnpm test -- CompactJobRow.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/CompactJobRow.tsx apps/web/src/components/CompactJobRow.test.tsx
git commit -m "feat(web): add CompactJobRow for chat result list"
```

---

### Task 10: Rewrite `Chat.tsx`

**Files:**
- Modify: `apps/web/src/pages/Chat.tsx`
- Test: `apps/web/src/pages/Chat.test.tsx` (new file)

**Interfaces:**
- Consumes: `Spinner` (Task 7), `useStatusTicker` (Task 8), `CompactJobRow` (Task 9), `ChatEvent`/narrative type (Task 6).

- [ ] **Step 1: Write the failing tests**

Create `apps/web/src/pages/Chat.test.tsx`:

```tsx
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Chat } from "./Chat";
import type { ChatEvent } from "../types";

vi.mock("../lib/sse", () => ({
  streamChat: vi.fn(),
}));

import { streamChat } from "../lib/sse";

function renderChat() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><Chat /></MemoryRouter>
    </QueryClientProvider>,
  );
}

async function sendMessage(text: string) {
  await userEvent.type(screen.getByPlaceholderText(/new grad/i), text);
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
}

describe("Chat", () => {
  it("shows a spinner and real status text while busy", async () => {
    let resolveStream!: () => void;
    vi.mocked(streamChat).mockImplementation(
      (_body: unknown, onEvent: (e: ChatEvent) => void) =>
        new Promise<void>((resolve) => {
          onEvent({ type: "status", text: "Reading your resume and preferences…" });
          resolveStream = resolve;
        }),
    );
    renderChat();
    await sendMessage("FDE in SF");
    expect(await screen.findByRole("status", { name: /loading/i })).toBeInTheDocument();
    expect(screen.getByText("Reading your resume and preferences…")).toBeInTheDocument();
    await act(async () => {
      resolveStream();
    });
  });

  it("renders the narrative paragraph and compact job list on results", async () => {
    vi.mocked(streamChat).mockImplementation(
      async (_body: unknown, onEvent: (e: ChatEvent) => void) => {
        onEvent({ type: "narrative", text: "Hey Brice, I found 1 great match." });
        onEvent({
          type: "result",
          job: {
            source: "ashby", company: "Ramp", title: "FDE", location: "SF",
            url: "https://x", score: 90, reason: "great",
          },
        });
        onEvent({ type: "done", count: 1 });
      },
    );
    renderChat();
    await sendMessage("FDE in SF");
    expect(await screen.findByText("Hey Brice, I found 1 great match.")).toBeInTheDocument();
    expect(screen.getByText("FDE")).toBeInTheDocument();
  });

  it("falls back to a plain count if done arrives with no narrative", async () => {
    vi.mocked(streamChat).mockImplementation(
      async (_body: unknown, onEvent: (e: ChatEvent) => void) => {
        onEvent({ type: "done", count: 0 });
      },
    );
    renderChat();
    await sendMessage("anything");
    expect(await screen.findByText("Found 0 roles.")).toBeInTheDocument();
  });

  it("shows the backend's no-results narrative when provided", async () => {
    vi.mocked(streamChat).mockImplementation(
      async (_body: unknown, onEvent: (e: ChatEvent) => void) => {
        onEvent({ type: "narrative", text: "I didn't find any roles matching that this time." });
        onEvent({ type: "done", count: 0 });
      },
    );
    renderChat();
    await sendMessage("anything");
    expect(
      await screen.findByText("I didn't find any roles matching that this time."),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && pnpm test -- Chat.test.tsx`
Expected: FAIL — old `Chat.tsx` doesn't render a `status` role, doesn't handle `narrative` events, still renders full `JobCard`s.

- [ ] **Step 3: Rewrite `Chat.tsx`**

Replace the full contents of `apps/web/src/pages/Chat.tsx`:

```tsx
import { useEffect, useReducer, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { streamChat } from "../lib/sse";
import { CompactJobRow } from "../components/CompactJobRow";
import { Spinner } from "../components/Spinner";
import { useStatusTicker } from "../lib/useStatusTicker";
import { useSaveJob } from "../queries";
import type { ChatEvent, RankedJob } from "../types";

type Item =
  | { kind: "user"; text: string }
  | { kind: "clarify"; text: string }
  | { kind: "narrative"; text: string }
  | { kind: "result"; job: RankedJob };

function reducer(items: Item[], ev: Item | { kind: "reset" }): Item[] {
  if (ev.kind === "reset") return [];
  return [...items, ev];
}

export function Chat() {
  const [items, dispatch] = useReducer(reducer, []);
  const [input, setInput] = useState("");
  const [convo, setConvo] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const gotNarrative = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const save = useSaveJob();
  const tickerText = useStatusTicker(busy, statusText);

  useEffect(() => () => abort.current?.abort(), []);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || busy) return;
    const message = input.trim();
    setInput("");
    dispatch({ kind: "user", text: message });
    setBusy(true);
    setStatusText("Getting started…"); // neutral placeholder — never a filler phrase
    gotNarrative.current = false;
    abort.current = new AbortController();
    try {
      await streamChat({ message, conversation_id: convo }, (ev: ChatEvent) => {
        if (ev.type === "status") setStatusText(ev.text);
        else if (ev.type === "clarify") dispatch({ kind: "clarify", text: ev.question });
        else if (ev.type === "narrative") {
          gotNarrative.current = true;
          dispatch({ kind: "narrative", text: ev.text });
        } else if (ev.type === "result") dispatch({ kind: "result", job: ev.job });
        else if (ev.type === "done" && !gotNarrative.current) {
          dispatch({
            kind: "narrative",
            text: `Found ${ev.count} role${ev.count === 1 ? "" : "s"}.`,
          });
        }
      }, abort.current.signal);
    } catch {
      dispatch({ kind: "narrative", text: "Something went wrong. Try again." });
    } finally {
      setBusy(false);
      setStatusText(null);
    }
  }

  function newChat() {
    dispatch({ kind: "reset" });
    setConvo(crypto.randomUUID());
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-3 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Find roles</h1>
        <div className="flex gap-3 text-sm">
          <Link className="text-blue-600" to="/saved">Saved jobs</Link>
          <button className="text-gray-600" onClick={newChat}>New chat</button>
        </div>
      </div>
      <div className="flex flex-col gap-3">
        {items.map((it, i) => {
          if (it.kind === "user")
            return <div key={i} className="self-end rounded bg-black px-3 py-2 text-white">{it.text}</div>;
          if (it.kind === "clarify")
            return <div key={i} className="rounded bg-gray-100 px-3 py-2">{it.text}</div>;
          if (it.kind === "narrative")
            return <p key={i} className="rounded bg-gray-50 px-3 py-3 leading-relaxed">{it.text}</p>;
          return (
            <CompactJobRow key={i} job={it.job} busy={save.isPending}
              onSave={() => save.mutate(it.job)} />
          );
        })}
        {busy && !gotNarrative.current && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Spinner />
            <span>{tickerText}</span>
          </div>
        )}
      </div>
      <form onSubmit={send} className="sticky bottom-4 mt-4 flex gap-2">
        <input className="flex-1 rounded border p-2" placeholder="e.g. new grad FDE roles in SF"
          value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} />
        <button className="rounded bg-black px-4 text-white" disabled={busy}>Send</button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm test -- Chat.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full frontend suite and typecheck**

Run: `cd apps/web && pnpm test && pnpm typecheck`
Expected: PASS — all tests (including untouched `JobCard.test.tsx`, `sse.test.ts`, `api.test.ts`).

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/pages/Chat.tsx apps/web/src/pages/Chat.test.tsx
git commit -m "feat(web): narrative results + status ticker in Chat"
```

---

### Task 11: Onboarding name field

**Files:**
- Modify: `apps/web/src/pages/Onboarding.tsx`
- Modify: `apps/web/src/pages/Onboarding.test.tsx`

**Interfaces:**
- Consumes: `PUT /api/profile/name` (Task 4), `api.put` (existing, `apps/web/src/api.ts`).

- [ ] **Step 1: Write the failing test**

Append to `apps/web/src/pages/Onboarding.test.tsx`:

```tsx
it("also submits the name when provided", async () => {
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify({ resume_text: "x", name: "Brice" }), {
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><Onboarding /></MemoryRouter>
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByPlaceholderText(/your first name/i), "Brice");
  const file = new File(["hi"], "resume.pdf", { type: "application/pdf" });
  await userEvent.upload(screen.getByLabelText("resume"), file);
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/profile/name",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ name: "Brice" }) }),
    ),
  );
  vi.unstubAllGlobals();
});
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `cd apps/web && pnpm test -- Onboarding.test.tsx`
Expected: existing test PASSes unchanged; new test FAILs — no name input exists yet (`getByPlaceholderText(/your first name/i)` throws).

- [ ] **Step 3: Add the name field to `Onboarding.tsx`**

Replace the full contents of `apps/web/src/pages/Onboarding.tsx`:

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

export function Onboarding() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const nav = useNavigate();
  const qc = useQueryClient();

  const [fileName, setFileName] = useState("");

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setBusy(true);
    setError("");
    try {
      await api.uploadFile("/profile/resume", file);
      if (name.trim()) await api.put("/profile/name", { name: name.trim() });
      await qc.invalidateQueries({ queryKey: ["profile"] });
      nav("/");
    } catch {
      setError("Upload failed — please use a PDF or DOCX.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-24 max-w-md p-6">
      <h1 className="text-2xl font-semibold">Upload your resume</h1>
      <p className="mt-2 text-gray-600">
        PDF or DOCX. We use it to match roles to you.
      </p>

      <label className="mt-6 block text-sm font-medium text-gray-700">
        What should we call you?
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your first name"
          disabled={busy}
          className="mt-1 w-full rounded border p-2 font-normal"
        />
      </label>

      <label
        className={`mt-6 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 px-6 py-10 text-center transition hover:border-black hover:bg-gray-50 ${
          busy ? "pointer-events-none opacity-60" : ""
        }`}
      >
        <span className="text-lg font-medium">
          {busy ? "Uploading…" : "Choose a PDF or DOCX file"}
        </span>
        <span className="mt-1 text-sm text-gray-500">
          {fileName || "Click here to browse"}
        </span>
        <input
          aria-label="resume"
          type="file"
          accept=".pdf,.docx"
          onChange={onFile}
          disabled={busy}
          className="hidden"
        />
      </label>

      {error && <p className="mt-3 text-red-600">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm test -- Onboarding.test.tsx`
Expected: PASS (both the existing upload test and the new name test — the existing test types no name, so `api.put` is never called and its assertions are unaffected)

- [ ] **Step 5: Run the full frontend suite and typecheck**

Run: `cd apps/web && pnpm test && pnpm typecheck`
Expected: PASS — full suite green.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/pages/Onboarding.tsx apps/web/src/pages/Onboarding.test.tsx
git commit -m "feat(web): collect user's name during onboarding"
```

---

## Final verification (after all tasks)

- [ ] `cd apps/api && uv run pytest -q && uv run ruff check . && uv run black --check .` — all green
- [ ] `cd apps/web && pnpm test && pnpm typecheck` — all green
- [ ] Manually smoke-test in the browser: sign up, enter a name + upload a resume on onboarding, send a chat message, confirm the spinner + status ticker appear, and the final response is a narrative paragraph followed by a compact job list with working Save buttons.
- [ ] Update `status.md` per the project's `CLAUDE.md` protocol.
