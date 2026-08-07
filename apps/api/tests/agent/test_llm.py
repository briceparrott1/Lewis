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
    llm = AnthropicLLM(
        client=_FakeClient([_TextBlock("hello there")]), model="fake-model"
    )
    out = await llm.complete(system="s", user="u")
    assert out == "hello there"


@pytest.mark.asyncio
async def test_complete_returns_empty_string_when_no_text_block():
    llm = AnthropicLLM(client=_FakeClient([]), model="fake-model")
    out = await llm.complete(system="s", user="u")
    assert out == ""
