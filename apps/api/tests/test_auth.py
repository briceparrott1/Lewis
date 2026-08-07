import uuid

from lewis_api.db.models import User


async def test_user_persists(db_session):
    user = User(email="a@b.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    assert isinstance(user.id, uuid.UUID)
    assert user.created_at is not None


COOKIE = "access_token"


async def test_signup_sets_cookie(client):
    resp = await client.post(
        "/api/auth/signup", json={"email": "x@y.com", "password": "hunter2"}
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "x@y.com"
    assert COOKIE in resp.cookies


async def test_login_and_me(client):
    await client.post(
        "/api/auth/signup", json={"email": "m@e.com", "password": "hunter2"}
    )
    login = await client.post(
        "/api/auth/login", json={"email": "m@e.com", "password": "hunter2"}
    )
    assert login.status_code == 200
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "m@e.com"


async def test_login_wrong_password(client):
    await client.post(
        "/api/auth/signup", json={"email": "w@e.com", "password": "hunter2"}
    )
    bad = await client.post(
        "/api/auth/login", json={"email": "w@e.com", "password": "nope"}
    )
    assert bad.status_code == 401


async def test_me_requires_auth(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
