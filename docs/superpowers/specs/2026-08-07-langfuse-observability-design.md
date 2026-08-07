# Langfuse Observability for Agent Sessions

## Problem

There is no way to retrospectively inspect what the agent actually did
during a chat session — which nodes ran, what was sent to Claude, what
came back, or how many tokens/what it cost. The only signal today is a
handful of `logging.getLogger` calls in `graph.py` and `chat/routes.py`,
relying on uvicorn's default logging. Debugging a bad ranking or a
strange narration means re-reading code, not looking at what happened.

## Goals

- See, per chat turn, which of the 5 graph nodes ran.
- See the actual prompt/completion/token usage for every LLM call made
  during that turn.
- Group everything under the existing session/user identity so a
  specific user's specific conversation can be pulled up.
- Zero behavior change when Langfuse isn't configured (dev-opt-in now,
  safe to leave un-configured in prod later).

## Non-goals (out of scope for this change)

- Self-hosting Langfuse (using Langfuse Cloud's free tier).
- Swapping the `MemorySaver` checkpointer for Postgres.
- Per-node `@observe()` instrumentation — the graph's 5 nodes are small
  and sequential; the callback handler's node-level spans (see below)
  already show the sequence without extra decorators.
- Langfuse's eval or prompt-management features.

## Design

### Where it plugs in

Two points, both additive to existing code paths:

1. **Graph-level structure** — a Langfuse `CallbackHandler` attached to
   the graph invocation in `run_agent()` (`agent/graph.py`). This gives
   one trace per chat turn showing the node sequence
   (`ingest → parse → clarify|search → respond`), for free, since
   LangGraph fires standard callback events per node regardless of what
   the nodes do internally.
2. **LLM-level detail** — `AnthropicLLM.structured()` and `.complete()`
   (`agent/llm.py`) wrap their calls to log a Langfuse *generation*
   (prompt, completion, model, token usage) nested under the current
   trace. This step is necessary because the codebase calls
   `anthropic.AsyncAnthropic` directly rather than through LangChain's
   `ChatAnthropic`, so the callback handler alone would only show empty
   node spans with no LLM content.

### Session/user identity mapping

`chat/routes.py` already builds `thread_id = f"{user.id}:{conversation_id}"`
and passes it as the LangGraph checkpointer key. Reuse it directly:

- Langfuse `session_id` = `thread_id` (one Langfuse session per
  conversation, matching the existing checkpointer grouping).
- Langfuse `user_id` = `user.id`.

No new identifiers are introduced.

### Configuration

New `Settings` fields in `config.py`, following the existing
`anthropic_api_key: str = ""` pattern (empty-string default, read from
root `.env` via `pydantic-settings`):

- `langfuse_public_key: str = ""`
- `langfuse_secret_key: str = ""`
- `langfuse_host: str = "https://cloud.langfuse.com"`

`.env.example` gets the two key entries documented (host is a sane
default, not required).

### Error handling / no-op behavior

When `langfuse_public_key`/`langfuse_secret_key` are unset (the default
in tests, CI, and any environment without them configured), tracing
must be fully inert:

- No network calls.
- No added latency on the chat request path.
- No possibility of a Langfuse-side failure breaking a chat response.

This mirrors how the codebase already treats `anthropic_api_key` being
unset elsewhere — guard construction of the callback handler / Langfuse
client on the keys being present, and skip attaching it entirely
otherwise. Langfuse's Python SDK also batches/sends trace data on a
background thread when it is active, so even a Langfuse outage while
configured shouldn't be able to block or fail a chat turn.

### Dependency

Add `langfuse` to `apps/api/pyproject.toml`. Exact SDK version and the
precise current API for the callback handler / generation logging
(Langfuse has shipped SDK v2 → v3 changes) should be confirmed against
current Langfuse docs at implementation time rather than assumed here.

## Testing

- No new mocking of Langfuse itself is needed: with keys unset by
  default, the existing 62 backend tests continue to exercise the
  no-op path implicitly.
- Add one explicit test asserting `run_agent()` (or the graph
  invocation path) does not raise and behaves identically when Langfuse
  env vars are absent — makes the no-op guarantee explicit rather than
  incidental.

## Privacy note

Resume content and job data will flow through prompts/completions sent
to Langfuse Cloud, a third-party service. Acceptable for this project's
current scale and purpose; worth revisiting if the user base or data
sensitivity changes before self-hosting is reconsidered.
