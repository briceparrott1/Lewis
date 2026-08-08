import langfuse
import langfuse.langchain
import pytest
from langfuse._client.resource_manager import LangfuseResourceManager

from lewis_api.agent.tracing import (
    init_langfuse,
    langfuse_run_config,
    observe_generation,
    shutdown_langfuse,
)
from lewis_api.config import get_settings


@pytest.fixture
def disabled_langfuse(monkeypatch):
    """Explicitly force the unconfigured state, rather than relying on the
    ambient environment having no LANGFUSE_* values set."""
    settings = get_settings()
    monkeypatch.setattr(settings, "langfuse_public_key", "")
    monkeypatch.setattr(settings, "langfuse_secret_key", "")
    return settings


def _reset_langfuse_singleton() -> None:
    """Tear down the process-wide Langfuse singleton registry safely.

    `Langfuse(...)` registers a singleton per public_key in
    `LangfuseResourceManager._instances`, not something scoped to
    `get_settings()`'s cache -- so it must be cleared between tests or it
    leaks into (and holds background threads open for) the rest of the suite.

    `LangfuseResourceManager.reset()` looks like the built-in way to do this,
    but in langfuse 4.14.3 it calls `.shutdown()` unconditionally on every
    registered instance, even ones already shut down (e.g. by a test that
    itself calls `shutdown_langfuse()`). A second `.shutdown()` call re-runs
    `flush()` -> `tracer_provider.force_flush()` against the OTel batch
    processor's background thread, which already exited after the first
    shutdown -- verified empirically to hang forever, not raise. So we
    replicate `reset()` here but guard each instance's own `_shutdown` flag
    first, skipping the redundant (hanging) shutdown call.
    """
    with LangfuseResourceManager._lock:
        for instance in list(LangfuseResourceManager._instances.values()):
            if not instance._shutdown:
                instance.shutdown()
        LangfuseResourceManager._instances.clear()


@pytest.fixture
def configured_langfuse(monkeypatch):
    """Explicitly force a configured state with fake-but-realistic-looking
    credentials. Langfuse batches/queues rather than calling out synchronously
    at construction time, so this needs no real network access.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-lf-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-lf-test")
    monkeypatch.setattr(settings, "langfuse_host", "https://cloud.langfuse.com")
    yield settings
    shutdown_langfuse()
    _reset_langfuse_singleton()


def test_langfuse_run_config_is_empty_when_unconfigured(disabled_langfuse):
    assert langfuse_run_config("user-1", "thread-1") == {}


def test_observe_generation_yields_noop_when_unconfigured(disabled_langfuse):
    with observe_generation("test", "fake-model", "prompt") as generation:
        generation.update(output="anything", usage_details={"input": 1, "output": 2})
    # Reaching here without raising proves the no-op path is safe.


def test_init_and_shutdown_are_safe_noops_when_unconfigured(disabled_langfuse):
    init_langfuse()
    shutdown_langfuse()


def test_langfuse_run_config_returns_callbacks_and_metadata_when_configured(
    configured_langfuse,
):
    config = langfuse_run_config("user-1", "thread-1")

    assert "callbacks" in config
    assert "metadata" in config
    assert config["metadata"]["langfuse_session_id"] == "thread-1"
    assert config["metadata"]["langfuse_user_id"] == "user-1"


def test_observe_generation_update_works_when_configured(configured_langfuse):
    with observe_generation("test-gen", "claude-haiku", "hello") as generation:
        generation.update(output="world", usage_details={"input": 1, "output": 2})
    # Reaching here without raising, using the real (wrapped) Langfuse
    # generation object, proves start_as_current_observation() -- the fixed
    # SDK call -- actually matches the installed langfuse package's API.


def test_init_and_shutdown_do_not_raise_when_configured(configured_langfuse):
    init_langfuse()
    shutdown_langfuse()


def test_langfuse_run_config_fails_open_when_langfuse_raises(
    configured_langfuse, monkeypatch
):
    def boom(*_args, **_kwargs):
        raise ModuleNotFoundError("simulated: langchain not installed")

    monkeypatch.setattr(langfuse.langchain, "CallbackHandler", boom)

    assert langfuse_run_config("user-1", "thread-1") == {}


def test_observe_generation_fails_open_when_langfuse_raises(
    configured_langfuse, monkeypatch
):
    def boom(*_args, **_kwargs):
        raise AttributeError(
            "'Langfuse' object has no attribute 'start_as_current_generation'"
        )

    monkeypatch.setattr(langfuse, "get_client", boom)

    with observe_generation("test-gen", "claude-haiku", "hello") as generation:
        generation.update(output="world", usage_details={"input": 1, "output": 2})
    # Reaching here without raising proves the enabled path fails open exactly
    # the way Critical 1 needed it to.


def test_init_langfuse_fails_open_when_langfuse_raises(
    configured_langfuse, monkeypatch
):
    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated Langfuse construction failure")

    monkeypatch.setattr(langfuse, "Langfuse", boom)

    init_langfuse()  # must not raise


def test_shutdown_langfuse_fails_open_when_langfuse_raises(
    configured_langfuse, monkeypatch
):
    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated Langfuse shutdown failure")

    monkeypatch.setattr(langfuse, "get_client", boom)

    shutdown_langfuse()  # must not raise
