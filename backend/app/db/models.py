"""SQLAlchemy models for `tasks` and `task_events`.

No relationship() anywhere: events are queried directly, which avoids async lazy loading.
CHECK constraints are built from the domain enums here; the migration hard-codes the same lists.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.tasks import Kind, Module, ReasonCode, TaskStatus

from .types import UTCDateTime

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _in_list(column: str, values: type) -> str:
    quoted = ", ".join(f"'{v.value}'" for v in values)
    return f"{column} IN ({quoted})"


PARAMS_TYPE = JSON().with_variant(JSONB(), "postgresql")


class TaskRow(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(_in_list("module", Module), name="module"),
        CheckConstraint(_in_list("kind", Kind), name="kind"),
        CheckConstraint(_in_list("status", TaskStatus), name="status"),
        CheckConstraint("NOT (module = 'tickets' AND kind = 'book')", name="no_ticket_booking"),
        Index("ix_tasks_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    module: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))
    params: Mapped[dict[str, Any]] = mapped_column(PARAMS_TYPE)
    status: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class TaskEventRow(Base):
    __tablename__ = "task_events"
    __table_args__ = (
        CheckConstraint(
            f"from_status IS NULL OR {_in_list('from_status', TaskStatus)}", name="from_status"
        ),
        CheckConstraint(_in_list("to_status", TaskStatus), name="to_status"),
        CheckConstraint(_in_list("reason_code", ReasonCode), name="reason_code"),
    )

    # Primary key (task_id, version): orders a task's events and stops two events claiming the
    # same version. It also serves lookups by task_id, so there is no separate index.
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
