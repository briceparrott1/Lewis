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
