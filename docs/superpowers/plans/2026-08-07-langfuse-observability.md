# Langfuse Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a developer retrospectively inspect a chat session in Langfuse Cloud — which of the 5 graph nodes ran, and the actual prompt/completion/token usage for every LLM call made during that turn.

**Architecture:** A new `agent/tracing.py` module centralizes all Langfuse touchpoints behind functions that are true no-ops when unconfigured. `run_agent()` (`agent/graph.py`) attaches a Langfuse `CallbackHandler` to the graph invocation for node-level trace structure. `AnthropicLLM` (`agent/llm.py`) wraps its two methods to log each raw Anthropic call as a nested Langfuse generation (prompt/completion/tokens), since those calls bypass LangChain and the callback handler alone can't see inside them.

**Tech Stack:** `langfuse` Python SDK (current v3+, OTel-based — `langfuse.langchain.CallbackHandler`, `langfuse.get_client().start_as_current_generation(...)`; NOT the legacy v2 `@observe`-decorator-only API), FastAPI lifespan, existing `pydantic-settings` `Settings` pattern.

## Global Constraints

- Every Langfuse touchpoint must be a true no-op (no network calls, no exceptions, no added latency) when `langfuse_public_key`/`langfuse_secret_key` are unset. This is the default in tests/CI and must not change their behavior.
- Langfuse `session_id` = existing `thread_id` (`f"{user.id}:{conversation_id}"`, already the checkpointer key). Langfuse `user_id` = existing `user.id`. No new identifiers are introduced.
- Initialize the Langfuse client explicitly from our own `Settings` values (`Langfuse(public_key=..., secret_key=..., host=...)`), not by relying on the SDK reading `LANGFUSE_*` from `os.environ` — `pydantic-settings` parses `.env` into `Settings` internally and does not populate `os.environ`, so env-var auto-pickup would silently fail to find credentials `Settings` itself can see. This matches the existing `AnthropicLLM` pattern, which already passes `api_key=settings.anthropic_api_key` explicitly rather than relying on `ANTHROPIC_API_KEY` auto-pickup.
- Definition of done for every task: `ruff check .` and `black --check .` clean, all tests passing (`uv run pytest -q` from `apps/api`).

---

### Task 1: `agent/tracing.py` — Langfuse helpers, dependency, and config

**Files:**
- Modify: `apps/api/pyproject.toml` (via `uv add langfuse`)
- Modify: `apps/api/lewis_api/config.py:9-20`
- Modify: `.env.example` (repo root)
- Create: `apps/api/lewis_api/agent/tracing.py`
- Test: `apps/api/tests/agent/test_tracing.py`

**Interfaces:**
- Produces (used by Tasks 2 and 3):
  - `langfuse_run_config(user_id: str, thread_id: str) -> dict` — extra LangGraph run-config (`callbacks` + `metadata`); `{}` when unconfigured.
  - `observe_generation(name: str, model: str, prompt) -> context manager` — yields an object with `.update(output=..., usage_details=...)`; yields a no-op object when unconfigured.
  - `init_langfuse() -> None` and `shutdown_langfuse() -> None` — process-wide client lifecycle; no-ops when unconfigured.

- [ ] **Step 1: Add the dependency**

```bash
cd apps/api && uv add langfuse
```

This updates `pyproject.toml` and `uv.lock` and installs into `.venv`. Confirm it succeeded:

```bash
uv run python -c "import langfuse; print(langfuse.__version__)"
```

Expected: prints a version string (v3 or later), no import error.

- [ ] **Step 2: Add config settings**

In `apps/api/lewis_api/config.py`, add after the existing `agent_model` line (currently line 20):

```python
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
```

- [ ] **Step 3: Document the new env vars**

In `.env.example` (repo root), add after `AGENT_MODEL=claude-haiku-4-5-20251001`:

```
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

- [ ] **Step 4: Write the failing tests**

Create `apps/api/tests/agent/test_tracing.py`:

```python
import pytest

from lewis_api.agent.tracing import (
    init_langfuse,
    langfuse_run_config,
    observe_generation,
    shutdown_langfuse,
)


def test_langfuse_run_config_is_empty_when_unconfigured():
    assert langfuse_run_config("user-1", "thread-1") == {}


def test_observe_generation_yields_noop_when_unconfigured():
    with observe_generation("test", "fake-model", "prompt") as generation:
        generation.update(output="anything", usage_details={"input": 1, "output": 2})
    # Reaching here without raising proves the no-op path is safe.


def test_init_and_shutdown_are_safe_noops_when_unconfigured():
    init_langfuse()
    shutdown_langfuse()
```

These rely on the test environment's default `Settings` (no `LANGFUSE_*` values set anywhere in `.env`/CI), matching how every other test in the suite already runs unconfigured.

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/agent/test_tracing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lewis_api.agent.tracing'`

- [ ] **Step 6: Implement `agent/tracing.py`**

```python
"""Optional Langfuse tracing for agent chat sessions. Every function here is a
true no-op — no network calls, no exceptions — when Langfuse isn't configured."""

from contextlib import contextmanager
from typing import Any

from lewis_api.config import get_settings


def _enabled() -> bool:
    settings = get_settings()
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def init_langfuse() -> None:
    """Initialize the process-wide Langfuse client from Settings. No-op when unconfigured."""
    if not _enabled():
        return
    from langfuse import Langfuse

    settings = get_settings()
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


def shutdown_langfuse() -> None:
    """Flush and stop the Langfuse client. No-op when unconfigured."""
    if not _enabled():
        return
    from langfuse import get_client

    get_client().shutdown()


def langfuse_run_config(user_id: str, thread_id: str) -> dict[str, Any]:
    """Extra LangGraph run-config (callback handler + session/user metadata).
    Returns {} when unconfigured, so merging it into a config dict is always safe."""
    if not _enabled():
        return {}
    from langfuse.langchain import CallbackHandler

    return {
        "callbacks": [CallbackHandler()],
        "metadata": {
            "langfuse_session_id": thread_id,
            "langfuse_user_id": user_id,
        },
    }


class _NoopGeneration:
    def update(self, **_kwargs: Any) -> None:
        pass


@contextmanager
def observe_generation(name: str, model: str, prompt: Any):
    """Log a raw Anthropic call as a nested Langfuse generation. Yields an
    object with .update(output=..., usage_details=...); no-op when unconfigured."""
    if not _enabled():
        yield _NoopGeneration()
        return
    from langfuse import get_client

    with get_client().start_as_current_generation(
        name=name, model=model, input=prompt
    ) as generation:
        yield generation
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_tracing.py -v`
Expected: PASS (3 passed)

- [ ] **Step 8: Commit**

```bash
git add apps/api/pyproject.toml apps/api/uv.lock apps/api/lewis_api/config.py \
        .env.example apps/api/lewis_api/agent/tracing.py apps/api/tests/agent/test_tracing.py
git commit -m "feat: add Langfuse tracing helpers (no-op when unconfigured)"
```

---

### Task 2: Attach Langfuse callback handler to the graph run

**Files:**
- Modify: `apps/api/lewis_api/agent/graph.py:110-137` (`run_agent`)

**Interfaces:**
- Consumes: `langfuse_run_config(user_id: str, thread_id: str) -> dict` from Task 1.

- [ ] **Step 1: Add the import**

In `apps/api/lewis_api/agent/graph.py`, add to the imports (near the other `lewis_api.agent.*` imports, e.g. after line 13):

```python
from lewis_api.agent.tracing import langfuse_run_config
```

- [ ] **Step 2: Merge the Langfuse run-config into `run_agent`'s config**

Change lines 120-121 from:

```python
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {
```

to:

```python
    config = {"configurable": {"thread_id": thread_id}}
    config.update(langfuse_run_config(user_id, thread_id))
    inputs = {
```

- [ ] **Step 3: Run the existing graph test suite to confirm no regression**

Run: `cd apps/api && uv run pytest tests/agent/test_graph.py -v`
Expected: PASS (all 6 tests) — `langfuse_run_config` returns `{}` in this environment (unconfigured), so `config.update({})` is a no-op and every existing assertion holds unchanged. This is the explicit proof that `run_agent()` behaves identically without Langfuse configured.

- [ ] **Step 4: Commit**

```bash
git add apps/api/lewis_api/agent/graph.py
git commit -m "feat: attach Langfuse callback handler to agent graph runs"
```

---

### Task 3: Log Anthropic calls as Langfuse generations

**Files:**
- Modify: `apps/api/lewis_api/agent/llm.py`
- Test: `apps/api/tests/agent/test_llm.py` (existing — must keep passing)

**Interfaces:**
- Consumes: `observe_generation(name: str, model: str, prompt) -> context manager` from Task 1.

**Note:** The existing test fakes in `test_llm.py` (`_Resp`, `_FakeClient`) don't set a `.usage` attribute. Both `structured()` and `complete()` must read `resp.usage` defensively (`getattr(resp, "usage", None)`) so this task doesn't break those tests — real Anthropic responses always have `.usage`, so this loses no functionality in production.

- [ ] **Step 1: Run the existing tests to confirm the current baseline**

Run: `cd apps/api && uv run pytest tests/agent/test_llm.py -v`
Expected: PASS (2 passed) — this is the regression baseline for this task.

- [ ] **Step 2: Rewrite `agent/llm.py`**

```python
from typing import Protocol

from anthropic import AsyncAnthropic

from lewis_api.agent.tracing import observe_generation
from lewis_api.config import get_settings


class LLM(Protocol):
    async def structured(
        self, system: str, user: str, tool_name: str, schema: dict
    ) -> dict: ...

    async def complete(self, system: str, user: str) -> str: ...


def _usage_details(resp) -> dict | None:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    return {"input": usage.input_tokens, "output": usage.output_tokens}


class AnthropicLLM:
    def __init__(self, client: AsyncAnthropic | None = None, model: str | None = None):
        settings = get_settings()
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.agent_model

    async def structured(
        self, system: str, user: str, tool_name: str, schema: dict
    ) -> dict:
        with observe_generation(
            tool_name, self._model, {"system": system, "user": user}
        ) as generation:
            resp = await self._client.messages.create(
                model=self._model,
                # Ranking ~50 jobs needs well over 1500 output tokens; a low cap
                # truncates the tool call and yields empty results. Billing is on
                # actual output, so a high ceiling is free insurance.
                max_tokens=8192,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[
                    {"name": tool_name, "description": tool_name, "input_schema": schema}
                ],
                tool_choice={"type": "tool", "name": tool_name},
            )
            result = {}
            for block in resp.content:
                if block.type == "tool_use":
                    result = dict(block.input)
                    break
            generation.update(output=result, usage_details=_usage_details(resp))
            return result

    async def complete(self, system: str, user: str) -> str:
        with observe_generation(
            "complete", self._model, {"system": system, "user": user}
        ) as generation:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            result = ""
            for block in resp.content:
                if block.type == "text":
                    result = block.text
                    break
            generation.update(output=result, usage_details=_usage_details(resp))
            return result
```

- [ ] **Step 3: Run the tests to verify they still pass**

Run: `cd apps/api && uv run pytest tests/agent/test_llm.py -v`
Expected: PASS (2 passed) — confirms the `getattr`-guarded usage extraction doesn't break on response fakes without `.usage`.

- [ ] **Step 4: Run the full backend suite as a broader regression check**

Run: `cd apps/api && uv run pytest -q`
Expected: all tests pass (was 62 before this plan started; +3 from Task 1 = 65).

- [ ] **Step 5: Commit**

```bash
git add apps/api/lewis_api/agent/llm.py
git commit -m "feat: log Anthropic calls as Langfuse generations"
```

---

### Task 4: Initialize/shut down the Langfuse client with the app lifecycle

**Files:**
- Modify: `apps/api/lewis_api/main.py`
- Test: `apps/api/tests/test_main.py` (new)

**Interfaces:**
- Consumes: `init_langfuse() -> None`, `shutdown_langfuse() -> None` from Task 1.

**Note:** `httpx`'s `ASGITransport` (used by the `client` fixture in `conftest.py`) never runs the app's `lifespan`, so no existing test exercises this wiring. `init_langfuse()`/`shutdown_langfuse()` are no-ops when unconfigured by design (Task 1), so there's no *observable* difference in behavior to red/green test here — this task adds a direct regression test that the lifespan still runs cleanly end-to-end with the new calls wired in, rather than a strict TDD-red step.

- [ ] **Step 1: Wire `init_langfuse`/`shutdown_langfuse` into the lifespan**

In `apps/api/lewis_api/main.py`, add to the imports (after line 9, `from lewis_api.agent.llm import AnthropicLLM`):

```python
from lewis_api.agent.tracing import init_langfuse, shutdown_langfuse
```

Change the `lifespan` function (currently lines 18-31) from:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    seed = load_seed()

    async def fetch_boards(entries, _client):
        async with httpx.AsyncClient(timeout=8) as client:
            return await fetch_all_boards(entries, client)

    # MemorySaver keeps this minimal for v1; swap for AsyncPostgresSaver to
    # persist clarify state across restarts (see docs/superpowers plan notes).
    app.state.agent_graph = build_graph(
        AnthropicLLM(), fetch_boards, seed, MemorySaver()
    )
    yield
```

to:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_langfuse()
    seed = load_seed()

    async def fetch_boards(entries, _client):
        async with httpx.AsyncClient(timeout=8) as client:
            return await fetch_all_boards(entries, client)

    # MemorySaver keeps this minimal for v1; swap for AsyncPostgresSaver to
    # persist clarify state across restarts (see docs/superpowers plan notes).
    app.state.agent_graph = build_graph(
        AnthropicLLM(), fetch_boards, seed, MemorySaver()
    )
    yield
    shutdown_langfuse()
```

- [ ] **Step 2: Write the regression test**

Create `apps/api/tests/test_main.py`:

```python
import pytest

from lewis_api.main import app, lifespan


@pytest.mark.asyncio
async def test_lifespan_builds_agent_graph_without_langfuse_configured():
    async with lifespan(app):
        assert app.state.agent_graph is not None
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `cd apps/api && uv run pytest tests/test_main.py -v`
Expected: PASS — proves the lifespan runs `init_langfuse()`/`shutdown_langfuse()` without raising when Langfuse is unconfigured (the only case exercised in this environment).

- [ ] **Step 4: Commit**

```bash
git add apps/api/lewis_api/main.py apps/api/tests/test_main.py
git commit -m "feat: init/shutdown Langfuse client with app lifespan"
```

---

### Task 5: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd apps/api && uv run pytest -q`
Expected: all tests pass (65 total: the pre-existing 62 + 3 new in `test_tracing.py`; `test_main.py`'s test is new too — confirm final count and that there are 0 failures).

- [ ] **Step 2: Run lint**

Run: `cd apps/api && uv run ruff check .`
Expected: no errors. If any, fix them (likely import-order or unused-import issues) and re-run.

- [ ] **Step 3: Run format check**

Run: `cd apps/api && uv run black --check .`
Expected: no reformatting needed. If it fails, run `uv run black .` and re-check.

- [ ] **Step 4: Commit any lint/format fixes**

Only if Steps 2-3 required changes:

```bash
git add -A
git commit -m "chore: lint/format fixes"
```
