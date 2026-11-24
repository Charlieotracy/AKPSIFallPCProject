"""Seed a local development database with a few tasks (CUJ 2).

Run from backend/ after `uv run alembic upgrade head`:  uv run python scripts/seed_dev.py
Refuses unless APP_ENV=local, and refuses if any task already exists.
Uses only the service layer, so every row obeys the same rules as real tasks.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from app.api.deps import DEV_USER_ID
from app.config import Settings
from app.db.models import TaskRow
from app.db.session import make_engine, make_sessionmaker
from app.domain.tasks import ReasonCode as R
from app.domain.tasks import TaskStatus as S
from app.services.tasks import create_task, transition

# (module, kind, initial status, [(next status, reason), ...], params)
DEV_TASKS = [
    ("courses", "search", S.READY, [], {}),
    ("courses", "search", S.READY, [(S.SEARCHING, R.SEARCH_STARTED), (S.DONE, R.RESULTS_READY)], {}),
    (
        "cbtf",
        "book",
        S.READY,
        [
            (S.SEARCHING, R.SEARCH_STARTED),
            (S.CANDIDATES, R.CANDIDATES_READY),
            (S.AWAITING_CONFIRM, R.CANDIDATE_SELECTED),
        ],
        {"course": "CS 354"},
    ),
    ("courses", "watch", S.READY, [(S.WATCHING, R.WATCH_STARTED)], {"course": "ECE 230"}),
    ("uhs", "book", S.NEEDS_INFO, [], {"category": "primary_care"}),  # no free text
]


async def seed() -> None:
    settings = Settings()
    if settings.app_env != "local":
        sys.exit("seed_dev.py only runs with APP_ENV=local")
    engine = make_engine(settings.resolved_database_url)
    sessionmaker = make_sessionmaker(engine)
    try:
        async with sessionmaker() as session, session.begin():
            existing = (await session.execute(select(func.count()).select_from(TaskRow))).scalar_one()
            if existing:
                sys.exit(
                    "database already has tasks; to start fresh, delete jev_uw_local.db "
                    "and run `uv run alembic upgrade head`"
                )
            seeds = [(DEV_USER_ID, *t) for t in DEV_TASKS]
            seeds.append(("other-user", "courses", "search", S.READY, [], {}))
            for user_id, module, kind, initial, steps, params in seeds:
                task = await create_task(
                    session,
                    user_id=user_id,
                    module=module,
                    kind=kind,
                    params=params,
                    initial_status=initial,
                )
                for to_status, reason in steps:
                    task = await transition(
                        session,
                        user_id=user_id,
                        task_id=task.id,
                        expected_version=task.version,
                        to_status=to_status,
                        reason=reason,
                    )
                print(f"{user_id:10} {module:8} {kind:6} {task.status:16} {task.id}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
