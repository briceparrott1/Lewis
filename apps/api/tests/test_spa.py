async def test_api_routes_still_work_without_build(client):
    # With no dist/ built, /api/health must still return JSON (SPA catch-all guarded)
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
