"""Engine and session wiring.

Async rules (design doc, "Database sessions"):
- expire_on_commit=False, so loaded objects keep their values after commit;
- one session per request, passed explicitly to service functions;
- hide_parameters=True, so SQLAlchemy errors don't echo bound values such as params.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url: str) -> AsyncEngine:
    is_sqlite = url.startswith("sqlite")
    engine = create_async_engine(
        url,
        hide_parameters=True,
        connect_args={"timeout": 5} if is_sqlite else {},
    )
    if is_sqlite:
        # Async engines don't take pool events directly; register on the sync engine.
        event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session
