import pytest

import lewis_api.chat.routes as chat_routes
from lewis_api.main import app


async def _signup(client, email="chat@e.com"):
    await client.post("/api/auth/signup", json={"email": email, "password": "hunter2"})


@pytest.mark.asyncio
async def test_chat_streams_events_and_requires_auth(client, monkeypatch):
    # unauthenticated
    r = await client.post("/api/chat", json={"message": "hi", "conversation_id": "c1"})
    assert r.status_code == 401

    async def fake_run_agent(*args, **kwargs):
        yield {"type": "status", "text": "Scanning…"}
        yield {
            "type": "result",
            "job": {
                "title": "FDE",
                "url": "u",
                "company": "Ramp",
                "location": "SF",
                "score": 90,
                "reason": "x",
                "source": "ashby",
            },
        }
        yield {"type": "done", "count": 1, "served_keys": ["u"]}

    monkeypatch.setattr(chat_routes, "run_agent", fake_run_agent)

    # httpx's ASGITransport doesn't run the app lifespan, so agent_graph is
    # never set on app.state; the monkeypatched run_agent ignores it anyway.
    app.state.agent_graph = object()

    await _signup(client)
    r = await client.post(
        "/api/chat", json={"message": "FDE in SF", "conversation_id": "c1"}
    )
    assert r.status_code == 200
    body = r.text
    assert "event: status" in body and "event: result" in body and "event: done" in body
    # served_jobs recorded
    jobs = await client.get("/api/jobs")  # not saved automatically
    assert jobs.status_code == 200


@pytest.mark.asyncio
async def test_chat_passes_user_name_to_agent(client, monkeypatch):
    await _signup(client, "named@e.com")
    await client.put("/api/profile/name", json={"name": "Brice"})

    captured = {}

    async def fake_run_agent(*args, **kwargs):
        captured.update(kwargs)
        yield {"type": "done", "count": 0, "served_keys": []}

    monkeypatch.setattr(chat_routes, "run_agent", fake_run_agent)
    app.state.agent_graph = object()

    r = await client.post("/api/chat", json={"message": "hi", "conversation_id": "c1"})
    assert r.status_code == 200
    assert captured["user_name"] == "Brice"


@pytest.mark.asyncio
async def test_chat_seeds_prior_prefs_from_profile_and_persists_final_prefs(
    client, monkeypatch
):
    await _signup(client, "prefs@e.com")
    captured = []

    async def fake_run_agent(*args, **kwargs):
        captured.append(kwargs["prior_prefs"])
        yield {
            "type": "done",
            "count": 0,
            "served_keys": [],
            "prefs": {"role_keywords": ["fde"]},
        }

    monkeypatch.setattr(chat_routes, "run_agent", fake_run_agent)
    app.state.agent_graph = object()

    r1 = await client.post(
        "/api/chat", json={"message": "fde jobs", "conversation_id": "c1"}
    )
    assert r1.status_code == 200
    assert captured[0] == {}  # nothing stored yet

    prof = await client.get("/api/profile")
    assert prof.json()["structured_prefs"] == {"role_keywords": ["fde"]}

    # New conversation_id (simulates "New chat") — prefs must still carry over
    r2 = await client.post(
        "/api/chat", json={"message": "anything else", "conversation_id": "c2"}
    )
    assert r2.status_code == 200
    assert captured[1] == {"role_keywords": ["fde"]}
