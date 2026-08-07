import os

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from lewis_api.db import models  # noqa: F401  (registers all tables on Base)
from lewis_api.db.base import Base, get_session
from lewis_api.main import app

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    # Separate DB from the dev/migration DB so the suite's create_all/drop_all
    # never corrupts migration state in `lewis`.
    "postgresql+asyncpg://lewis:lewis_local_dev@localhost:5432/lewis_test",
)


@pytest.fixture
async def _ensure_test_db():
    """Create the test database if it doesn't exist, so local dev never needs a
    manual `CREATE DATABASE`. (It persists in the Docker volume once created.)"""
    db_name = TEST_DB_URL.rsplit("/", 1)[1]
    admin_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
    engine = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(_ensure_test_db):
    """Fresh schema per test. NullPool keeps every connection on the test's own
    event loop, avoiding pytest-asyncio 'different event loop' errors with asyncpg.
    Cheap for our handful of small tables."""
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    session = maker()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def client(db_session):
    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
