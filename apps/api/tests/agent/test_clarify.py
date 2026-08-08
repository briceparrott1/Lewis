import pytest

from lewis_api.agent.clarify import CLARIFY_TEXT, stream_clarify_reply


class FakeLLM:
    def __init__(self, chunks=None, raise_exc=None):
        self.chunks = chunks or []
        self.raise_exc = raise_exc
        self.calls = []

    async def stream(self, system, user):
        self.calls.append((system, user))
        if self.raise_exc:
            raise self.raise_exc
        for c in self.chunks:
            yield c


@pytest.mark.asyncio
async def test_stream_clarify_reply_includes_message_and_missing_fields():
    llm = FakeLLM(chunks=["Hey! ", "Where are you looking, and what level?"])
    chunks = [c async for c in stream_clarify_reply("hi there", {}, llm)]
    assert chunks == ["Hey! ", "Where are you looking, and what level?"]
    _, user = llm.calls[0]
    assert "hi there" in user
    assert "role" in user
    assert "location or remote work" in user
    assert "seniority level" in user


@pytest.mark.asyncio
async def test_stream_clarify_reply_raises_on_llm_error():
    llm = FakeLLM(raise_exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        async for _ in stream_clarify_reply("hi", {}, llm):
            pass


def test_clarify_text_fallback_is_a_nonempty_static_string():
    assert isinstance(CLARIFY_TEXT, str) and CLARIFY_TEXT
