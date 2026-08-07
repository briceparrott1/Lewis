import pytest

from lewis_api.agent.rank import rank_jobs


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    async def structured(self, system, user, tool_name, schema):
        return self.payload


@pytest.mark.asyncio
async def test_rank_merges_and_sorts():
    cands = [
        {"external_id": "1", "title": "FDE", "url": "u1", "description": "x"},
        {"external_id": "2", "title": "SE", "url": "u2", "description": "y"},
    ]
    llm = FakeLLM(
        {
            "rankings": [
                {"external_id": "1", "score": 60, "reason": "ok"},
                {"external_id": "2", "score": 95, "reason": "great"},
            ]
        }
    )
    out = await rank_jobs(cands, {"role_keywords": ["fde"]}, "resume", llm)
    assert [j["external_id"] for j in out] == ["2", "1"]  # sorted by score desc
    assert out[0]["score"] == 95 and out[0]["reason"] == "great"
