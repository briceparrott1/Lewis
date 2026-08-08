"""Optional Langfuse tracing for agent chat sessions. Every function here is a
true no-op — no network calls, no exceptions — when Langfuse isn't configured,
and fails open (behaving as if unconfigured) if Langfuse itself errors out."""

import logging
import sys
from contextlib import contextmanager
from typing import Any

from lewis_api.config import get_settings

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    settings = get_settings()
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def init_langfuse() -> None:
    """Initialize the process-wide Langfuse client from Settings. No-op when unconfigured,
    fails open (logs and returns) if Langfuse itself raises."""
    if not _enabled():
        return
    try:
        from langfuse import Langfuse

        settings = get_settings()
        Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:
        logger.warning(
            "Langfuse init failed; continuing without tracing", exc_info=True
        )


def shutdown_langfuse() -> None:
    """Flush and stop the Langfuse client. No-op when unconfigured,
    fails open (logs and returns) if Langfuse itself raises."""
    if not _enabled():
        return
    try:
        from langfuse import get_client

        get_client().shutdown()
    except Exception:
        logger.warning("Langfuse shutdown failed", exc_info=True)


def langfuse_run_config(user_id: str, thread_id: str) -> dict[str, Any]:
    """Extra LangGraph run-config (callback handler + session/user metadata).
    Returns {} when unconfigured or when Langfuse itself fails, so merging it
    into a config dict is always safe."""
    if not _enabled():
        return {}
    try:
        from langfuse.langchain import CallbackHandler

        return {
            "callbacks": [CallbackHandler()],
            "metadata": {
                "langfuse_session_id": thread_id,
                "langfuse_user_id": user_id,
            },
        }
    except Exception:
        logger.warning(
            "Langfuse run config failed; tracing disabled for this run", exc_info=True
        )
        return {}


class _NoopGeneration:
    def update(self, **_kwargs: Any) -> None:
        pass


class _SafeGeneration:
    """Wraps a real Langfuse generation so a Langfuse-side failure inside
    .update() can't break the caller (fails open, logs a warning)."""

    def __init__(self, generation: Any) -> None:
        self._generation = generation

    def update(self, **kwargs: Any) -> None:
        try:
            self._generation.update(**kwargs)
        except Exception:
            logger.warning("Langfuse generation.update() failed", exc_info=True)


@contextmanager
def observe_generation(name: str, model: str, prompt: Any):
    """Log a raw Anthropic call as a nested Langfuse generation. Yields an
    object with .update(output=..., usage_details=...); no-op when unconfigured,
    and fails open (falls back to a no-op) if Langfuse itself errors on setup,
    teardown, or update — without swallowing the caller's own exceptions
    (e.g. a real failure in the wrapped Anthropic call)."""
    if not _enabled():
        yield _NoopGeneration()
        return

    try:
        from langfuse import get_client

        span_cm = get_client().start_as_current_observation(
            as_type="generation", name=name, model=model, input=prompt
        )
        generation = span_cm.__enter__()
    except Exception:
        logger.warning(
            "Langfuse generation setup failed; continuing without tracing",
            exc_info=True,
        )
        yield _NoopGeneration()
        return

    try:
        yield _SafeGeneration(generation)
    except BaseException:
        try:
            span_cm.__exit__(*sys.exc_info())
        except Exception:
            logger.warning("Langfuse generation teardown failed", exc_info=True)
        raise
    else:
        try:
            span_cm.__exit__(None, None, None)
        except Exception:
            logger.warning("Langfuse generation teardown failed", exc_info=True)
