import httpx
import pytest

from lewis_api.agent.sources.ashby import fetch_ashby
from lewis_api.agent.sources.greenhouse import fetch_greenhouse

GH_PAYLOAD = {
    "jobs": [
        {
            "id": 123,
            "title": "Forward Deployed Engineer",
            "absolute_url": "https://job-boards.greenhouse.io/gitlab/jobs/123",
            "location": {"name": "Remote, US"},
            "updated_at": "2026-08-01T00:00:00Z",
            "content": "<p>Build things</p>",
        }
    ]
}

ASHBY_PAYLOAD = {
    "jobs": [
        {
            "id": "uuid-1",
            "title": "Solutions Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/ramp/uuid-1",
            "applyUrl": "https://jobs.ashbyhq.com/ramp/uuid-1/application",
            "location": "New York",
            "department": "GTM",
            "publishedAt": "2026-08-02T00:00:00Z",
            "descriptionPlain": "Deploy with customers",
            "compensation": {"summary": "$150k"},
        }
    ]
}


def _client(payload):
    def handler(request):
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_fetch_greenhouse_maps_fields():
    async with _client(GH_PAYLOAD) as client:
        jobs = await fetch_greenhouse("gitlab", client)
    j = jobs[0]
    assert j["source"] == "greenhouse"
    assert j["board_token"] == "gitlab"
    assert j["external_id"] == "123"
    assert j["url"] == "https://job-boards.greenhouse.io/gitlab/jobs/123"
    assert j["location"] == "Remote, US"
    assert "Build things" in j["description"]  # HTML stripped


@pytest.mark.asyncio
async def test_fetch_ashby_maps_fields_and_uses_jobUrl():
    async with _client(ASHBY_PAYLOAD) as client:
        jobs = await fetch_ashby("ramp", client)
    j = jobs[0]
    assert j["source"] == "ashby"
    assert j["url"] == "https://jobs.ashbyhq.com/ramp/uuid-1"  # not applyUrl
    assert j["description"] == "Deploy with customers"
    assert j["department"] == "GTM"
