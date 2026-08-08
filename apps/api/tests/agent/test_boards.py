import logging

import httpx
import pytest

from lewis_api.agent.sources import boards
from lewis_api.agent.state import Job


@pytest.mark.asyncio
async def test_fetch_all_boards_merges_and_tolerates_failure(monkeypatch):
    async def fake_gh(token, client):
        return [Job(source="greenhouse", url=f"https://x/{token}/1", title="A")]

    async def fake_ashby(org, client):
        raise RuntimeError("boom")  # one board fails

    monkeypatch.setattr(boards, "fetch_greenhouse", fake_gh)
    monkeypatch.setattr(boards, "fetch_ashby", fake_ashby)
    boards._CACHE.clear()

    entries = [
        boards.SeedEntry("GitLab", "greenhouse", "gitlab"),
        boards.SeedEntry("Ramp", "ashby", "ramp"),
    ]
    jobs = await boards.fetch_all_boards(entries, client=None)
    assert len(jobs) == 1  # ashby failure skipped, gitlab kept
    assert jobs[0]["title"] == "A"


def test_default_concurrency_is_40():
    import inspect

    sig = inspect.signature(boards.fetch_all_boards)
    assert sig.parameters["concurrency"].default == 40


@pytest.mark.asyncio
async def test_fetch_attaches_entry_company_and_industry(monkeypatch):
    async def fake_gh(token, client):
        # fetcher returns the raw token as company, same as real fetch_greenhouse today
        return [
            Job(
                source="greenhouse",
                company=token,
                url=f"https://x/{token}/1",
                title="A",
            )
        ]

    monkeypatch.setattr(boards, "fetch_greenhouse", fake_gh)
    boards._CACHE.clear()

    entry = boards.SeedEntry("GitLab", "greenhouse", "gitlab", industry="devtools")
    jobs = await boards.fetch_all_boards([entry], client=None)
    assert (
        jobs[0]["company"] == "GitLab"
    )  # overlaid with the display name, not the raw token
    assert jobs[0]["industry"] == "devtools"


@pytest.mark.asyncio
async def test_rate_limited_board_logs_warning_and_fails_open(monkeypatch, caplog):
    async def fake_gh(token, client):
        request = httpx.Request("GET", "https://x")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError("rate limited", request=request, response=response)

    async def fake_ashby(org, client):
        return [Job(source="ashby", url=f"https://x/{org}/1", title="A")]

    monkeypatch.setattr(boards, "fetch_greenhouse", fake_gh)
    monkeypatch.setattr(boards, "fetch_ashby", fake_ashby)
    boards._CACHE.clear()

    entries = [
        boards.SeedEntry("GitLab", "greenhouse", "gitlab"),
        boards.SeedEntry("Ramp", "ashby", "ramp"),
    ]
    with caplog.at_level(logging.WARNING):
        jobs = await boards.fetch_all_boards(entries, client=None)
    assert len(jobs) == 1  # 429 board skipped, ashby kept
    assert any(
        "429" in r.message or "rate limit" in r.message.lower() for r in caplog.records
    )
