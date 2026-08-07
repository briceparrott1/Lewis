import pytest

from lewis_api.agent.narrate import narrate_results

RANKED = [
    {
        "external_id": "1",
        "title": "FDE",
        "company": "Ramp",
        "location": "SF",
        "score": 92,
        "reason": "Matches your backend + customer-facing experience",
    },
    {
        "external_id": "2",
        "title": "Support Engineer",
        "company": "GitLab",
        "location": "Remote",
        "score": 61,
        "reason": "Lower seniority but remote-friendly",
    },
]


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
async def test_narrate_calls_llm_with_context():
    llm = FakeLLM(text="Hey Brice, I found 2 roles for you...")
    out = await narrate_results(
        RANKED, {"role_keywords": ["fde"]}, "resume text", "Brice", llm
    )
    assert out == "Hey Brice, I found 2 roles for you..."
    assert len(llm.calls) == 1
    _, user = llm.calls[0]
    assert "Brice" in user
    assert "FDE" in user
    assert "Ramp" in user


@pytest.mark.asyncio
async def test_narrate_skips_llm_call_when_no_results():
    llm = FakeLLM(text="should not be used")
    out = await narrate_results(
        [], {"role_keywords": ["fde"]}, "resume text", "Brice", llm
    )
    assert out == (
        "I didn't find any roles matching that this time — try broadening your "
        "criteria (location, seniority, or role type) and I'll take another look."
    )
    assert llm.calls == []


@pytest.mark.asyncio
async def test_narrate_falls_back_on_llm_error():
    llm = FakeLLM(raise_exc=RuntimeError("boom"))
    out = await narrate_results(
        RANKED, {"role_keywords": ["fde"]}, "resume text", "Brice", llm
    )
    assert out == "I found 2 jobs matching your search."


@pytest.mark.asyncio
async def test_narrate_uses_generic_greeting_when_no_name():
    llm = FakeLLM(text="Hi there, found some roles.")
    out = await narrate_results(RANKED, {}, "resume", None, llm)
    assert out == "Hi there, found some roles."
    _, user = llm.calls[0]
    assert "there" in user
