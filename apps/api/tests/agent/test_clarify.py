import pytest

from lewis_api.agent.clarify import CLARIFY_TEXT, generate_clarify_reply


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
async def test_generate_clarify_reply_includes_message_and_missing_fields():
    llm = FakeLLM(text="Hey! Where are you looking, and what level?")
    out = await generate_clarify_reply("hi there", {}, llm)
    assert out == "Hey! Where are you looking, and what level?"
    _, user = llm.calls[0]
    assert "hi there" in user
    assert "role" in user
    assert "location or remote work" in user
    assert "seniority level" in user


@pytest.mark.asyncio
async def test_generate_clarify_reply_falls_back_on_llm_error():
    llm = FakeLLM(raise_exc=RuntimeError("boom"))
    out = await generate_clarify_reply("hi", {}, llm)
    assert out == CLARIFY_TEXT
