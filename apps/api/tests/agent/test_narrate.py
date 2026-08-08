import pytest

from lewis_api.agent.narrate import fallback_text, stream_narrative_results

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
async def test_stream_narrative_yields_chunks_with_context():
    llm = FakeLLM(chunks=["Hey Brice, ", "I found 2 roles..."])
    chunks = [
        c
        async for c in stream_narrative_results(
            RANKED, {"role_keywords": ["fde"]}, "resume text", "Brice", llm
        )
    ]
    assert chunks == ["Hey Brice, ", "I found 2 roles..."]
    assert len(llm.calls) == 1
    _, user = llm.calls[0]
    assert "Brice" in user
    assert "FDE" in user
    assert "Ramp" in user


@pytest.mark.asyncio
async def test_stream_narrative_skips_llm_call_when_no_results():
    llm = FakeLLM(chunks=["should not be used"])
    chunks = [
        c
        async for c in stream_narrative_results(
            [], {"role_keywords": ["fde"]}, "resume text", "Brice", llm
        )
    ]
    assert chunks == [
        (
            "I didn't find any roles matching that this time — try broadening your "
            "criteria (location, seniority, or role type) and I'll take another look."
        )
    ]
    assert llm.calls == []


@pytest.mark.asyncio
async def test_stream_narrative_raises_on_llm_error():
    llm = FakeLLM(raise_exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        async for _ in stream_narrative_results(
            RANKED, {"role_keywords": ["fde"]}, "resume text", "Brice", llm
        ):
            pass


@pytest.mark.asyncio
async def test_stream_narrative_uses_generic_greeting_when_no_name():
    llm = FakeLLM(chunks=["Hi there, found some roles."])
    chunks = [
        c async for c in stream_narrative_results(RANKED, {}, "resume", None, llm)
    ]
    assert chunks == ["Hi there, found some roles."]
    _, user = llm.calls[0]
    assert "there" in user


def test_fallback_text():
    assert fallback_text(1) == "I found 1 job matching your search."
    assert fallback_text(2) == "I found 2 jobs matching your search."
