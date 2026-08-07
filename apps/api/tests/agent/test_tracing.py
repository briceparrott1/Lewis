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
