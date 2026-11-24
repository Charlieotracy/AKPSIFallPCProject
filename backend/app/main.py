"""App factory. There is deliberately no module-level `app`: importing this module must not
read the environment. Run with `uvicorn app.main:create_app --factory`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, tasks
from app.config import Settings
from app.db.session import make_engine, make_sessionmaker


def create_app(settings: Settings | None = None) -> FastAPI:
    # Both lines can raise, so a misconfigured app fails before it is returned:
    # a forbidden dev identity fails in Settings(), a prod app without DATABASE_URL in the second.
    settings = settings or Settings()
    database_url = settings.resolved_database_url

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(database_url)
        app.state.engine = engine
        app.state.sessionmaker = make_sessionmaker(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Jev UW backend", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health.router)
    app.include_router(tasks.router)
    return app
