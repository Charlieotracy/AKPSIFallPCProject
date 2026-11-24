"""Concurrency tests (INV-4, Goal 6). Deterministic; they run on SQLite and PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from app.db.models import TaskEventRow, TaskRow
from app.domain.errors import VersionConflict
from app.domain.tasks import ReasonCode, TaskStatus
from app.services.tasks import apply_transition, load_task, transition

S = TaskStatus
R = ReasonCode


async def _state(sessionmaker, task_id):
    async with sessionmaker() as s:
        task = await s.get(TaskRow, task_id)
        events = list(
            (
                await s.execute(
                    select(TaskEventRow)
                    .where(TaskEventRow.task_id == task_id)
                    .order_by(TaskEventRow.version)
                )
            ).scalars()
        )
    return task, events


def _assert_first_writer_won(task, events):
    assert (task.status, task.version) == ("searching", 2)
    assert len(events) == 2
    assert (events[1].to_status, events[1].reason_code) == ("searching", "search_started")


async def test_stale_expected_version_raises_conflict(make_task, sessionmaker):
    task = await make_task(kind="book")
    async with sessionmaker() as s1, s1.begin():
        await transition(
            s1,
            user_id="dev-user",
            task_id=task.id,
            expected_version=1,
            to_status=S.SEARCHING,
            reason=R.SEARCH_STARTED,
        )
    with pytest.raises(VersionConflict):
        async with sessionmaker() as s2, s2.begin():
            await transition(
                s2,
                user_id="dev-user",
                task_id=task.id,
                expected_version=1,
                to_status=S.CANCELLED,
                reason=R.USER_CANCELLED,
            )
    _assert_first_writer_won(*await _state(sessionmaker, task.id))


async def test_interleaved_race_is_caught_by_compare_and_swap(make_task, sessionmaker):
    """A reads, B writes and commits, then A writes from its stale copy and must lose."""
    task = await make_task(kind="book")
    async with sessionmaker() as a:
        async with a.begin():  # commits on exit, so A holds no lock
            stale = await load_task(a, user_id="dev-user", task_id=task.id)

        async with sessionmaker() as b, b.begin():
            await transition(
                b,
                user_id="dev-user",
                task_id=task.id,
                expected_version=1,
                to_status=S.SEARCHING,
                reason=R.SEARCH_STARTED,
            )

        assert stale.version == 1  # expire_on_commit=False kept the stale values
        with pytest.raises(VersionConflict):
            async with a.begin():
                await apply_transition(a, stale, to_status=S.CANCELLED, reason=R.USER_CANCELLED)

    _assert_first_writer_won(*await _state(sessionmaker, task.id))


async def test_duplicate_event_version_is_rejected(make_task, sessionmaker):
    task = await make_task()
    with pytest.raises(IntegrityError):
        async with sessionmaker() as s, s.begin():
            await s.execute(
                insert(TaskEventRow.__table__).values(
                    task_id=task.id,
                    version=1,
                    from_status=None,
                    to_status="ready",
                    reason_code="created",
                    created_at=datetime.now(UTC),
                )
            )
