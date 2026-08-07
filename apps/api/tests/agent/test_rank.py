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


@pytest.mark.asyncio
async def test_rank_includes_seniority_and_falls_back_to_unknown():
    cands = [
        {"external_id": "1", "title": "New Grad SWE", "url": "u1", "description": "x"},
        {
            "external_id": "2",
            "title": "Staff Engineer",
            "url": "u2",
            "description": "y",
        },
        {"external_id": "3", "title": "Engineer", "url": "u3", "description": "z"},
    ]
    llm = FakeLLM(
        {
            "rankings": [
                {
                    "external_id": "1",
                    "score": 60,
                    "reason": "ok",
                    "seniority": "new_grad",
                },
                {
                    "external_id": "2",
                    "score": 95,
                    "reason": "great",
                    "seniority": "bogus-value",  # invalid -> falls back
                },
                {
                    "external_id": "3",
                    "score": 40,
                    "reason": "meh",
                    # no "seniority" key at all -> falls back
                },
            ]
        }
    )
    out = await rank_jobs(cands, {}, "resume", llm)
    by_id = {j["external_id"]: j for j in out}
    assert by_id["1"]["seniority"] == "new_grad"
    assert by_id["2"]["seniority"] == "unknown"
    assert by_id["3"]["seniority"] == "unknown"
