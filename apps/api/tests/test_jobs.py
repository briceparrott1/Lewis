async def _signup(client, email="j@e.com"):
    await client.post("/api/auth/signup", json={"email": email, "password": "hunter2"})


def _job_payload():
    return {
        "source": "ashby",
        "company": "Ramp",
        "title": "Forward Deployed Engineer",
        "location": "New York",
        "url": "https://jobs.ashbyhq.com/ramp/abc",
        "score": 92,
        "reason": "Strong FDE match",
    }


async def test_save_list_delete(client):
    await _signup(client)
    save = await client.post("/api/jobs", json=_job_payload())
    assert save.status_code == 201
    job_id = save.json()["id"]

    listing = await client.get("/api/jobs")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    delete = await client.delete(f"/api/jobs/{job_id}")
    assert delete.status_code == 204

    listing2 = await client.get("/api/jobs")
    assert listing2.json() == []


async def test_jobs_require_auth(client):
    resp = await client.get("/api/jobs")
    assert resp.status_code == 401


async def test_jobs_are_user_scoped(client):
    await _signup(client, "owner@e.com")
    await client.post("/api/jobs", json=_job_payload())
    await client.post("/api/auth/logout")
    await _signup(client, "other@e.com")
    listing = await client.get("/api/jobs")
    assert listing.json() == []
