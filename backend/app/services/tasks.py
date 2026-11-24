"""Task service: the only application code that creates tasks or changes their status.

Transaction rule: the caller owns the transaction (`async with session.begin():`). Nothing here
commits or rolls back, so a status change and its event are saved together or not at all.

`transition()` is the only supported way to change a status. `apply_transition()` is separate
only so the race test can call it with a stale copy of a task.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TaskEventRow, TaskRow
from app.db.types import utcnow
from app.domain.errors import IllegalTransition, InvalidTaskParams, TaskNotFound, VersionConflict
from app.domain.tasks import (
    INITIAL_STATUSES,
    Kind,
    Module,
    ReasonCode,
    TaskStatus,
    check_transition,
)

UHS_ALLOWED_KEYS = frozenset({"category", "earliest", "latest"})
_UHS_CATEGORY = re.compile(r"[a-z_]{1,32}")
LIST_LIMIT = 50


def _is_offset_aware_iso(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _check_creation_rules(module: Module, kind: Kind, params: Any) -> None:
    if not isinstance(params, dict):
        raise InvalidTaskParams("params must be a JSON object")
    try:
        json.dumps(params, allow_nan=False)
    except (TypeError, ValueError):
        raise InvalidTaskParams("params must contain only JSON-native values") from None

    if module is Module.UHS:
        extra = set(params) - UHS_ALLOWED_KEYS
        if extra:
            raise InvalidTaskParams(f"uhs params have unsupported keys: {sorted(extra)}")
        category = params.get("category")
        if category is not None and not (
            isinstance(category, str) and _UHS_CATEGORY.fullmatch(category)
        ):
            raise InvalidTaskParams("uhs category must be a short lowercase identifier")
        for key in ("earliest", "latest"):
            value = params.get(key)
            if value is not None and not _is_offset_aware_iso(value):
                raise InvalidTaskParams(f"uhs {key} must be an ISO-8601 datetime with an offset")

    if module is Module.TICKETS and kind is Kind.BOOK:
        raise InvalidTaskParams("tickets tasks can never be of kind book")


async def create_task(
    session: AsyncSession,
    *,
    user_id: str,
    module: Module,
    kind: Kind,
    params: dict[str, Any] | None,
    initial_status: TaskStatus,
) -> TaskRow:
    module, kind, initial_status = Module(module), Kind(kind), TaskStatus(initial_status)
    if initial_status not in INITIAL_STATUSES:
        raise IllegalTransition(f"a task cannot be created in {initial_status}")
    params = {} if params is None else params
    _check_creation_rules(module, kind, params)

    now = utcnow()
    task = TaskRow(
        id=uuid.uuid4(),
        user_id=user_id,
        module=module,
        kind=kind,
        params=params,
        status=initial_status,
        version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    await session.flush()  # insert the task before its first event
    session.add(
        TaskEventRow(
            task_id=task.id,
            version=1,
            from_status=None,
            to_status=initial_status,
            reason_code=ReasonCode.CREATED,
            created_at=now,
        )
    )
    await session.flush()
    return task


async def load_task(session: AsyncSession, *, user_id: str, task_id: uuid.UUID) -> TaskRow:
    result = await session.execute(
        select(TaskRow).where(TaskRow.id == task_id, TaskRow.user_id == user_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise TaskNotFound(f"task {task_id} not found")
    return task


async def apply_transition(
    session: AsyncSession, task: TaskRow, *, to_status: TaskStatus, reason: ReasonCode
) -> TaskRow:
    if not isinstance(reason, ReasonCode):
        raise TypeError("reason must be a ReasonCode")
    to_status = TaskStatus(to_status)
    # Snapshot first. Nothing below reads task.status or task.version after the UPDATE.
    old_status, old_version = TaskStatus(task.status), task.version
    check_transition(Kind(task.kind), old_status, to_status)

    result = await session.execute(
        update(TaskRow)
        .where(
            TaskRow.id == task.id,
            TaskRow.user_id == task.user_id,
            TaskRow.status == old_status,
            TaskRow.version == old_version,
        )
        .values(status=to_status, version=old_version + 1, updated_at=utcnow())
        # Keep SQLAlchemy from rewriting the in-memory task before the event is written.
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        raise VersionConflict(f"task {task.id} changed since version {old_version}")

    session.add(
        TaskEventRow(
            task_id=task.id,
            version=old_version + 1,
            from_status=old_status,
            to_status=to_status,
            reason_code=reason,
            created_at=utcnow(),
        )
    )
    await session.flush()
    await session.refresh(task)
    return task


async def transition(
    session: AsyncSession,
    *,
    user_id: str,
    task_id: uuid.UUID,
    expected_version: int,
    to_status: TaskStatus,
    reason: ReasonCode,
) -> TaskRow:
    task = await load_task(session, user_id=user_id, task_id=task_id)
    if task.version != expected_version:
        raise VersionConflict(f"task {task_id} is at version {task.version}")
    return await apply_transition(session, task, to_status=to_status, reason=reason)


async def list_tasks(
    session: AsyncSession, *, user_id: str, limit: int = LIST_LIMIT
) -> list[TaskRow]:
    result = await session.execute(
        select(TaskRow)
        .where(TaskRow.user_id == user_id)
        .order_by(TaskRow.created_at.desc(), TaskRow.id.desc())
        .limit(limit)
    )
    return list(result.scalars())
