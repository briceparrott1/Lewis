import pytest

from lewis_api.agent.prefs import is_sufficient, parse_prefs


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def structured(self, system, user, tool_name, schema):
        self.calls.append((system, user, tool_name))
        return self.payload


def test_is_sufficient_rule():
    assert is_sufficient({"role_keywords": ["fde"], "locations": ["SF"]}) is True
    assert is_sufficient({"role_keywords": ["fde"], "remote_ok": True}) is True
    assert is_sufficient({"role_keywords": ["fde"]}) is False
    assert is_sufficient({"locations": ["SF"]}) is False


@pytest.mark.asyncio
async def test_parse_prefs_merges_prior():
    llm = FakeLLM(
        {"role_keywords": ["fde"], "locations": ["SF"], "priorities": ["role"]}
    )
    prior = {"remote_ok": True}
    out = await parse_prefs("new grad FDE in SF", prior, "resume", llm)
    assert out["role_keywords"] == ["fde"]
    assert out["locations"] == ["SF"]
    assert out["remote_ok"] is True  # prior preserved
