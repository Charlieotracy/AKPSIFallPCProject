"""Shared test fixtures.

The suite runs on TEST_DATABASE_URL when it is set and not empty, otherwise on a fresh temporary
SQLite file. It never uses DATABASE_URL or .env. Never point TEST_DATABASE_URL at a database you
want to keep: every test deletes all rows afterwards.

Rule for test authors: close every session you open (`async with`). An open transaction makes
the cleanup DELETE wait forever on PostgreSQL.

Application modules are imported inside the fixtures that use them, never at the top of this
file, so conftest imports cleanly in every implementation phase.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or None
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
_SETTINGS_ENV_VARS = ("APP_ENV", "DEV_IDENTITY_ENABLED", "DATABASE_URL")


@pytest.fixture(autouse=True)
def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test sees the developer's shell settings."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Migrated once per session. Plain `def`: env.py's asyncio.run() needs no running loop."""
    from alembic import command
    from alembic.config import Config

    url = TEST_DATABASE_URL or f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}"
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")
    return url


@pytest.fixture
async def engine(database_url: str):
    from sqlalchemy import text

    from app.db.session import make_engine

    eng = make_engine(database_url)
    try:
        yield eng
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM task_events"))
            await conn.execute(text("DELETE FROM tasks"))
        await eng.dispose()


@pytest.fixture
def sessionmaker(engine):
    from app.db.session import make_sessionmaker

    return make_sessionmaker(engine)


@pytest.fixture
def test_settings(database_url: str):
    from app.config import Settings

    return Settings(
        _env_file=None, app_env="test", dev_identity_enabled=True, database_url=database_url
    )


@pytest.fixture
def make_task(sessionmaker):
    """Create a task through the service in its own committed transaction."""
    from sqlalchemy import update

    from app.db.models import TaskRow
    from app.services.tasks import create_task

    async def _make_task(
        *,
        user_id: str = "dev-user",
        module: str = "courses",
        kind: str = "search",
        params: dict | None = None,
        initial_status: str = "ready",
        created_at=None,
    ) -> TaskRow:
        async with sessionmaker() as session:
            async with session.begin():
                task = await create_task(
                    session,
                    user_id=user_id,
                    module=module,
                    kind=kind,
                    params=params,
                    initial_status=initial_status,
                )
                if created_at is not None:
                    await session.execute(
                        update(TaskRow)
                        .where(TaskRow.id == task.id)
                        .values(created_at=created_at, updated_at=created_at)
                        .execution_options(synchronize_session=False)
                    )
            await session.refresh(task)
            return task

    return _make_task


@pytest.fixture
def make_client():
    """Build an app from `settings`, run its lifespan, and yield an HTTP client for it."""
    import httpx
    from app.main import create_app

    @asynccontextmanager
    async def _make_client(settings):
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                yield client

    return _make_client


@pytest.fixture
async def client(make_client, test_settings, engine):
    # Depends on `engine` so rows are cleaned up after API tests too.
    async with make_client(test_settings) as c:
        yield c
