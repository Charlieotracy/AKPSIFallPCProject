"""Pydantic response models: the JSON contract for task routes.

A later PR exports these to JSON Schema and TypeScript for the extension.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.tasks import Kind, Module, TaskStatus


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    module: Module
    kind: Kind
    status: TaskStatus
    version: int
    params: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    # user_id is deliberately not exposed.


class TaskList(BaseModel):
    items: list[TaskOut]
