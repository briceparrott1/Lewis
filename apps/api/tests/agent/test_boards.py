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
