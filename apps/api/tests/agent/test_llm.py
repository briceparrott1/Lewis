import pytest

from lewis_api.agent.llm import AnthropicLLM


class _FinalMessage:
    def __init__(self, usage=None):
        self.usage = usage


class _FakeMessageStream:
    def __init__(self, chunks, final):
        self._chunks = chunks
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _gen(self):
        for c in self._chunks:
            yield c

    @property
    def text_stream(self):
        return self._gen()

    async def get_final_message(self):
        return self._final


class _FakeMessages:
    def __init__(self, chunks, final):
        self._chunks = chunks
        self._final = final

    def stream(self, **kwargs):
        return _FakeMessageStream(self._chunks, self._final)


class _FakeClient:
    def __init__(self, chunks, final=None):
        self.messages = _FakeMessages(chunks, final or _FinalMessage())


@pytest.mark.asyncio
async def test_stream_yields_chunks_in_order():
    llm = AnthropicLLM(client=_FakeClient(["Hel", "lo ", "there"]), model="fake-model")
    chunks = [c async for c in llm.stream(system="s", user="u")]
    assert chunks == ["Hel", "lo ", "there"]


@pytest.mark.asyncio
async def test_stream_yields_nothing_for_empty_response():
    llm = AnthropicLLM(client=_FakeClient([]), model="fake-model")
    chunks = [c async for c in llm.stream(system="s", user="u")]
    assert chunks == []
