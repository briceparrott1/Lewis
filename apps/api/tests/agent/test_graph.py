import pytest
from langgraph.checkpoint.memory import MemorySaver

from lewis_api.agent.graph import build_graph, run_agent
from lewis_api.agent.sources.seed import SeedEntry


class FakeLLM:
    def __init__(
        self, prefs_payload, rank_payload, narrative_text="Here's what I found."
    ):
        self.prefs_payload = prefs_payload
        self.rank_payload = rank_payload
        self.narrative_text = narrative_text
        self.complete_calls = []

    async def structured(self, system, user, tool_name, schema):
        if tool_name == "record_preferences":
            return self.prefs_payload
        return self.rank_payload

    async def complete(self, system, user):
        self.complete_calls.append(user)
        return self.narrative_text


async def _fake_fetch(entries, client):
    return [
        {
            "source": "ashby",
            "company": "Ramp",
            "board_token": "ramp",
            "external_id": "1",
            "title": "Forward Deployed Engineer",
            "location": "SF",
            "url": "https://jobs.ashbyhq.com/ramp/1",
            "description": "d",
        },
        {
            "source": "greenhouse",
            "company": "GitLab",
            "board_token": "gitlab",
            "external_id": "2",
            "title": "Barista",
            "location": "SF",
            "url": "https://boards.greenhouse.io/gitlab/2",
            "description": "d",
        },
    ]


def _graph(prefs_payload, rank_payload):
    llm = FakeLLM(prefs_payload, rank_payload)
    seed = [SeedEntry("Ramp", "ashby", "ramp")]
    return build_graph(llm, _fake_fetch, seed, MemorySaver()), llm


@pytest.mark.asyncio
async def test_clear_query_streams_results_and_reports_served():
    graph, llm = _graph(
        {
            "role_keywords": ["forward deployed"],
            "locations": ["SF"],
            "required": ["role"],
        },
        {"rankings": [{"external_id": "1", "score": 90, "reason": "great FDE"}]},
    )
    events = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            prior_prefs={},
            served_keys=[],
            message="FDE in SF",
            thread_id="u1:c1",
            user_name="Brice",
        )
    ]
    types = [e["type"] for e in events]
    # parse + scan + filter + rank + writing-up = 5 real status phases
    assert types.count("status") == 5
    assert "narrative" in types and "result" in types and types[-1] == "done"
    assert types.index("narrative") < types.index("result")
    results = [e for e in events if e["type"] == "result"]
    assert results[0]["job"]["title"] == "Forward Deployed Engineer"  # barista filtered
    assert events[-1]["served_keys"] == ["https://jobs.ashbyhq.com/ramp/1"]
    # Proves the run_agent -> AgentState -> respond -> narrate_results hop
    # actually threads user_name through, not just the two endpoints.
    assert any("Brice" in call for call in llm.complete_calls)


@pytest.mark.asyncio
async def test_vague_query_asks_one_clarify_then_searches():
    graph, _llm = _graph(
        {"role_keywords": ["engineer"]},  # no location/remote → insufficient
        {"rankings": [{"external_id": "1", "score": 80, "reason": "ok"}]},
    )
    first = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            prior_prefs={},
            served_keys=[],
            message="I want a tech job",
            thread_id="u1:c2",
        )
    ]
    types_first = [e["type"] for e in first]
    assert first[0]["type"] == "status"  # "Reading your resume..." comes first now
    assert "clarify" in types_first and types_first[-1] == "done"

    # second turn, same thread — now proceeds (clarified_once persists)
    first_prefs = first[-1]["prefs"]
    second = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            prior_prefs=first_prefs,
            served_keys=[],
            message="in SF",
            thread_id="u1:c2",
        )
    ]
    assert any(e["type"] == "result" for e in second)
    assert any(e["type"] == "narrative" for e in second)


@pytest.mark.asyncio
async def test_served_jobs_excluded():
    graph, _llm = _graph(
        {
            "role_keywords": ["forward deployed"],
            "locations": ["SF"],
            "required": ["role"],
        },
        {"rankings": [{"external_id": "1", "score": 90, "reason": "x"}]},
    )
    events = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            prior_prefs={},
            served_keys=["https://jobs.ashbyhq.com/ramp/1"],  # already served
            message="FDE in SF",
            thread_id="u1:c3",
        )
    ]
    assert not any(e["type"] == "result" for e in events)  # only match excluded
    narrative_events = [e for e in events if e["type"] == "narrative"]
    assert len(narrative_events) == 1
    assert "didn't find any roles" in narrative_events[0]["text"]


@pytest.mark.asyncio
async def test_respond_applies_company_diversity_cap():
    async def fetch_many(entries, client):
        jobs = [
            {
                "source": "greenhouse",
                "company": "Acme",
                "board_token": "acme",
                "external_id": f"acme-{i}",
                "title": "Software Engineer",
                "location": "SF",
                "url": f"https://boards.greenhouse.io/acme/{i}",
                "description": "d",
            }
            for i in range(4)
        ]
        jobs.append(
            {
                "source": "ashby",
                "company": "Beta",
                "board_token": "beta",
                "external_id": "beta-1",
                "title": "Software Engineer",
                "location": "SF",
                "url": "https://jobs.ashbyhq.com/beta/1",
                "description": "d",
            }
        )
        return jobs

    rank_payload = {
        "rankings": [
            {
                "external_id": f"acme-{i}",
                "score": 90 - i,
                "reason": "x",
                "seniority": "unknown",
            }
            for i in range(4)
        ]
        + [
            {
                "external_id": "beta-1",
                "score": 50,
                "reason": "x",
                "seniority": "unknown",
            }
        ]
    }
    llm = FakeLLM(
        {"role_keywords": ["engineer"], "locations": ["SF"], "required": ["role"]},
        rank_payload,
    )
    seed = [SeedEntry("Acme", "greenhouse", "acme")]
    graph = build_graph(llm, fetch_many, seed, MemorySaver())
    events = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            prior_prefs={},
            served_keys=[],
            message="SWE in SF",
            thread_id="u1:c4",
        )
    ]
    results = [e["job"] for e in events if e["type"] == "result"]
    companies = [j["company"] for j in results]
    assert companies.count("Acme") <= 2
    assert "Beta" in companies


@pytest.mark.asyncio
async def test_respond_excludes_seniority_mismatch():
    async def fetch_two(entries, client):
        return [
            {
                "source": "greenhouse",
                "company": "Acme",
                "board_token": "acme",
                "external_id": "senior-role",
                "title": "Senior Software Engineer",
                "location": "SF",
                "url": "https://boards.greenhouse.io/acme/1",
                "description": "d",
            },
            {
                "source": "greenhouse",
                "company": "Acme",
                "board_token": "acme",
                "external_id": "mid-role",
                "title": "Mid-level Software Engineer",
                "location": "SF",
                "url": "https://boards.greenhouse.io/acme/2",
                "description": "d",
            },
        ]

    rank_payload = {
        "rankings": [
            {
                "external_id": "senior-role",
                "score": 90,
                "reason": "x",
                "seniority": "senior",
            },
            {
                "external_id": "mid-role",
                "score": 80,
                "reason": "x",
                "seniority": "mid",  # one tier below "senior" -> excluded
            },
        ]
    }
    llm = FakeLLM(
        {
            "role_keywords": ["engineer"],
            "locations": ["SF"],
            "required": ["role"],
            "seniority": "senior",
        },
        rank_payload,
    )
    seed = [SeedEntry("Acme", "greenhouse", "acme")]
    graph = build_graph(llm, fetch_two, seed, MemorySaver())
    events = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            prior_prefs={},
            served_keys=[],
            message="senior SWE in SF",
            thread_id="u1:c5",
        )
    ]
    results = [e["job"] for e in events if e["type"] == "result"]
    assert [j["external_id"] for j in results] == ["senior-role"]


@pytest.mark.asyncio
async def test_done_event_reports_final_merged_prefs():
    graph, _llm = _graph(
        {"role_keywords": ["fde"], "locations": ["SF"], "required": ["role"]},
        {"rankings": []},
    )
    events = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            prior_prefs={"remote_ok": True},
            served_keys=[],
            message="FDE in SF",
            thread_id="u1:c6",
        )
    ]
    done = events[-1]
    assert done["type"] == "done"
    assert done["prefs"]["role_keywords"] == ["fde"]
    assert done["prefs"]["remote_ok"] is True  # prior preserved
