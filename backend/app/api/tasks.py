"""Read-only task routes, scoped to the current user.

Another user's task returns 404, the same as a missing one, so its existence isn't revealed.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.db.session import get_session
from app.domain.errors import TaskNotFound
from app.schemas.tasks import TaskList, TaskOut
from app.services.tasks import list_tasks, load_task

router = APIRouter(prefix="/tasks", tags=["tasks"])

UserDep = Annotated[CurrentUser, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=TaskList)
async def get_tasks(user: UserDep, session: SessionDep) -> TaskList:
    rows = await list_tasks(session, user_id=user.id)
    return TaskList(items=[TaskOut.model_validate(row) for row in rows])


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: UUID, user: UserDep, session: SessionDep) -> TaskOut:
    try:
        row = await load_task(session, user_id=user.id, task_id=task_id)
    except TaskNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found") from None
    return TaskOut.model_validate(row)
