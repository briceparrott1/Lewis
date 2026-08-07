from lewis_api.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_roundtrip():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_jwt_roundtrip():
    token = create_access_token("user-123")
    assert decode_access_token(token) == "user-123"


def test_jwt_rejects_garbage():
    assert decode_access_token("not.a.jwt") is None
