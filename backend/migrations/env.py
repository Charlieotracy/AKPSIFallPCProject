"""Alembic environment (async).

The URL comes from a test override (config.attributes["database_url"]) when present; otherwise
from app.config.Settings, which applies the same fail-closed rules as the app. Settings() is only
built when there is no override.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.config import Settings
from app.db.models import Base
from app.db.session import make_engine

config = context.config
override_url = config.attributes.get("database_url")

# Tests pass an override and keep their own logging setup.
if config.config_file_name is not None and not override_url:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    return override_url or Settings().resolved_database_url


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # required on SQLite, harmless on PostgreSQL
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    engine = make_engine(_database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline migrations are not supported")

asyncio.run(_run_async_migrations())
