import uuid

from lewis_api.db.models import User


async def test_user_persists(db_session):
    user = User(email="a@b.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    assert isinstance(user.id, uuid.UUID)
    assert user.created_at is not None
