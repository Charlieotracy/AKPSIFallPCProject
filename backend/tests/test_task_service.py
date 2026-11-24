"""Service tests against the database (INV-1, INV-5, INV-6, INV-7; Goals 3, 7, 8).

Raw inserts use Core insert(...__table__) and expect IntegrityError from the database itself.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, insert, inspect, select
from sqlalchemy.exc import IntegrityError

from app.db.models import TaskEventRow, TaskRow
from app.domain.errors import (
    GuardedTransition,
    IllegalTransition,
    InvalidTaskParams,
    TaskNotFound,
)
from app.domain.tasks import Kind, Module, ReasonCode, TaskStatus
from app.services.tasks import create_task, transition

S = TaskStatus
R = ReasonCode


async def _reload(sessionmaker, task_id):
    async with sessionmaker() as s:
        return await s.get(TaskRow, task_id)


async def _events(sessionmaker, task_id):
    async with sessionmaker() as s:
        result = await s.execute(
            select(TaskEventRow).where(TaskEventRow.task_id == task_id).order_by(
                TaskEventRow.version
            )
        )
        return list(result.scalars())


async def _count(sessionmaker, model):
    async with sessionmaker() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


def _task_values(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "user_id": "dev-user",
        "module": "courses",
        "kind": "search",
        "params": {},
        "status": "ready",
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return values


async def _raw_insert(sessionmaker, table, **values):
    async with sessionmaker() as s, s.begin():
        await s.execute(insert(table).values(**values))


# --- persistence -------------------------------------------------------------------------


async def test_task_round_trips_with_utc_timestamps(make_task, sessionmaker):
    task = await make_task(module="cbtf", kind="book", params={"course": "CS 354"})
    loaded = await _reload(sessionmaker, task.id)
    assert (loaded.user_id, loaded.module, loaded.kind) == ("dev-user", "cbtf", "book")
    assert loaded.params == {"course": "CS 354"}
    assert (loaded.status, loaded.version) == ("ready", 1)
    assert loaded.created_at.tzinfo is not None
    assert loaded.created_at.utcoffset().total_seconds() == 0


async def test_creation_writes_a_created_event(make_task, sessionmaker):
    task = await make_task(initial_status="needs_info")
    [event] = await _events(sessionmaker, task.id)
    assert (event.version, event.from_status, event.to_status, event.reason_code) == (
        1,
        None,
        "needs_info",
        "created",
    )


@pytest.mark.parametrize("status", [s for s in TaskStatus if s not in (S.NEEDS_INFO, S.READY)])
async def test_task_cannot_start_outside_initial_statuses(make_task, status):
    with pytest.raises(IllegalTransition):
        await make_task(initial_status=status)


# --- creation rules (INV-6) --------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"category": "primary_care", "reason": "headache"},
        {"category": "I feel anxious"},
        {"category": "primary_care\n"},
        {"earliest": "after my appointment about my anxiety"},
        {"earliest": "2026-12-01T09:00"},  # naive: no UTC offset
        {"latest": 12},
    ],
)
async def test_uhs_params_rejected(make_task, sessionmaker, params):
    before = await _count(sessionmaker, TaskRow)
    with pytest.raises(InvalidTaskParams):
        await make_task(module="uhs", kind="book", params=params)
    assert await _count(sessionmaker, TaskRow) == before


@pytest.mark.parametrize(
    "params",
    [
        {"category": "primary_care", "earliest": "2026-12-01T09:00:00-06:00"},
        {"category": None, "earliest": None, "latest": None},
        {},
    ],
)
async def test_uhs_params_accepted(make_task, params):
    task = await make_task(module="uhs", kind="book", initial_status="needs_info", params=params)
    assert task.params == params


@pytest.mark.parametrize("params", [{"when": datetime.now(UTC)}, {"x": float("nan")}, ["a"]])
async def test_non_json_params_rejected(make_task, params):
    with pytest.raises(InvalidTaskParams):
        await make_task(params=params)


async def test_ticket_booking_rejected_by_service(make_task):
    with pytest.raises(InvalidTaskParams):
        await make_task(module="tickets", kind="book")


# --- database CHECK constraints ----------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "overrides"),
    [
        ("tasks", {"module": "bogus"}),  # ck_tasks_module
        ("tasks", {"kind": "bogus"}),  # ck_tasks_kind
        ("tasks", {"status": "bogus"}),  # ck_tasks_status
        ("tasks", {"module": "tickets", "kind": "book"}),  # ck_tasks_no_ticket_booking
        ("task_events", {"from_status": "bogus"}),  # ck_task_events_from_status
        ("task_events", {"to_status": "bogus"}),  # ck_task_events_to_status
        ("task_events", {"reason_code": "free text reason"}),  # ck_task_events_reason_code
    ],
)
async def test_every_check_constraint_rejects_a_bad_value(make_task, sessionmaker, table, overrides):
    if table == "tasks":
        with pytest.raises(IntegrityError):
            await _raw_insert(sessionmaker, TaskRow.__table__, **_task_values(**overrides))
    else:
        task = await make_task()
        values = {
            "task_id": task.id,
            "version": 2,
            "from_status": "ready",
            "to_status": "searching",
            "reason_code": "search_started",
            "created_at": datetime.now(UTC),
        }
        values.update(overrides)
        with pytest.raises(IntegrityError):
            await _raw_insert(sessionmaker, TaskEventRow.__table__, **values)


async def test_every_enum_value_is_accepted_by_the_database(make_task, sessionmaker):
    # Catches an enum that drifts from the migration's literal value lists.
    for status in TaskStatus:
        await _raw_insert(sessionmaker, TaskRow.__table__, **_task_values(status=status.value))
    for module in Module:
        for kind in Kind:
            if (module, kind) == (Module.TICKETS, Kind.BOOK):
                continue
            await _raw_insert(
                sessionmaker,
                TaskRow.__table__,
                **_task_values(module=module.value, kind=kind.value),
            )
    task = await make_task()
    for version, reason in enumerate(ReasonCode, start=2):
        await _raw_insert(
            sessionmaker,
            TaskEventRow.__table__,
            task_id=task.id,
            version=version,
            from_status="ready",
            to_status="ready",
            reason_code=reason.value,
            created_at=datetime.now(UTC),
        )


async def test_event_foreign_key_is_enforced(sessionmaker):
    with pytest.raises(IntegrityError):
        await _raw_insert(
            sessionmaker,
            TaskEventRow.__table__,
            task_id=uuid.uuid4(),
            version=1,
            from_status=None,
            to_status="ready",
            reason_code="created",
            created_at=datetime.now(UTC),
        )


# --- transitions -------------------------------------------------------------------------


async def test_successful_transition_bumps_version_and_writes_one_event(make_task, sessionmaker):
    task = await make_task()
    async with sessionmaker() as s, s.begin():
        updated = await transition(
            s,
            user_id="dev-user",
            task_id=task.id,
            expected_version=1,
            to_status=S.SEARCHING,
            reason=R.SEARCH_STARTED,
        )
    assert (updated.status, updated.version) == ("searching", 2)
    assert updated.updated_at >= task.updated_at
    events = await _events(sessionmaker, task.id)
    assert [(e.version, e.from_status, e.to_status, e.reason_code) for e in events] == [
        (1, None, "ready", "created"),
        (2, "ready", "searching", "search_started"),
    ]


@pytest.mark.parametrize(
    ("kind", "path", "target", "error"),
    [
        ("search", [], S.CANDIDATES, IllegalTransition),  # no ready -> candidates edge
        ("search", [S.SEARCHING], S.CANDIDATES, IllegalTransition),  # edge is book-only
        (
            "book",
            [S.SEARCHING, S.CANDIDATES, S.AWAITING_CONFIRM],
            S.EXECUTING,
            GuardedTransition,
        ),
    ],
)
async def test_rejected_transitions_change_nothing(make_task, sessionmaker, kind, path, target, error):
    task = await make_task(kind=kind)
    version = 1
    for status in path:
        async with sessionmaker() as s, s.begin():
            await transition(
                s,
                user_id="dev-user",
                task_id=task.id,
                expected_version=version,
                to_status=status,
                reason=R.SEARCH_STARTED,
            )
        version += 1
    before = await _reload(sessionmaker, task.id)
    with pytest.raises(error):
        async with sessionmaker() as s, s.begin():
            await transition(
                s,
                user_id="dev-user",
                task_id=task.id,
                expected_version=version,
                to_status=target,
                reason=R.CANDIDATE_SELECTED,
            )
    after = await _reload(sessionmaker, task.id)
    assert (after.status, after.version) == (before.status, before.version)
    assert len(await _events(sessionmaker, task.id)) == version


async def test_update_and_event_insert_are_atomic(make_task, sessionmaker):
    """INV-1: if the event insert fails, the status update is rolled back with it."""
    task = await make_task()
    await _raw_insert(
        sessionmaker,
        TaskEventRow.__table__,
        task_id=task.id,
        version=2,
        from_status="ready",
        to_status="searching",
        reason_code="search_started",
        created_at=datetime.now(UTC),
    )
    with pytest.raises(IntegrityError):
        async with sessionmaker() as s, s.begin():
            await transition(
                s,
                user_id="dev-user",
                task_id=task.id,
                expected_version=1,
                to_status=S.SEARCHING,
                reason=R.SEARCH_STARTED,
            )
    after = await _reload(sessionmaker, task.id)
    assert (after.status, after.version) == ("ready", 1)


async def test_reason_must_be_a_reason_code(make_task, sessionmaker):
    task = await make_task()
    with pytest.raises(TypeError):
        async with sessionmaker() as s, s.begin():
            await transition(
                s,
                user_id="dev-user",
                task_id=task.id,
                expected_version=1,
                to_status=S.SEARCHING,
                reason="search_started",
            )


# --- scoping and event shape -------------------------------------------------------------


async def test_other_users_task_is_not_found(make_task, sessionmaker):
    task = await make_task(user_id="other-user")
    for task_id in (task.id, uuid.uuid4()):
        with pytest.raises(TaskNotFound):
            async with sessionmaker() as s, s.begin():
                await transition(
                    s,
                    user_id="dev-user",
                    task_id=task_id,
                    expected_version=1,
                    to_status=S.SEARCHING,
                    reason=R.SEARCH_STARTED,
                )


async def test_task_events_columns_are_content_free(engine):
    async with engine.connect() as conn:
        columns = await conn.run_sync(lambda c: inspect(c).get_columns("task_events"))
    assert {c["name"] for c in columns} == {
        "task_id",
        "version",
        "from_status",
        "to_status",
        "reason_code",
        "created_at",
    }


async def test_create_task_validates_module_value(sessionmaker):
    with pytest.raises(ValueError):
        async with sessionmaker() as s, s.begin():
            await create_task(
                s,
                user_id="dev-user",
                module="bogus",
                kind="search",
                params={},
                initial_status="ready",
            )
