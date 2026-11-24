"""Create tasks and task_events.

Hand-written. Value lists are literals on purpose: a migration must never import the domain
enums, or editing an enum later would silently change what this migration does.
tests/test_task_service.py checks that every current enum value is accepted by these constraints.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.db.types import UTCDateTime

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODULES = "'courses', 'uhs', 'cbtf', 'tickets'"
KINDS = "'search', 'book', 'watch'"
STATUSES = (
    "'needs_info', 'ready', 'searching', 'awaiting_login', 'candidates', 'awaiting_confirm', "
    "'executing', 'watching', 'done', 'failed', 'handed_off', 'cancelled'"
)
REASONS = (
    "'created', 'info_provided', 'missing_info', 'search_started', 'login_required', "
    "'login_completed', 'results_ready', 'candidates_ready', 'candidate_selected', "
    "'candidate_changed', 'booking_succeeded', 'booking_failed', 'outcome_unknown', "
    "'not_bookable_online', 'watch_started', 'watch_ended', 'user_cancelled', 'internal_error'"
)


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("module", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("params", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
        sa.CheckConstraint(f"module IN ({MODULES})", name=op.f("ck_tasks_module")),
        sa.CheckConstraint(f"kind IN ({KINDS})", name=op.f("ck_tasks_kind")),
        sa.CheckConstraint(f"status IN ({STATUSES})", name=op.f("ck_tasks_status")),
        sa.CheckConstraint(
            "NOT (module = 'tickets' AND kind = 'book')", name=op.f("ck_tasks_no_ticket_booking")
        ),
    )
    op.create_index(op.f("ix_tasks_user_id_created_at"), "tasks", ["user_id", "created_at"])

    op.create_table(
        "task_events",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("task_id", "version", name=op.f("pk_task_events")),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_task_events_task_id_tasks")
        ),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({STATUSES})",
            name=op.f("ck_task_events_from_status"),
        ),
        sa.CheckConstraint(f"to_status IN ({STATUSES})", name=op.f("ck_task_events_to_status")),
        sa.CheckConstraint(
            f"reason_code IN ({REASONS})", name=op.f("ck_task_events_reason_code")
        ),
    )


def downgrade() -> None:
    op.drop_table("task_events")
    op.drop_index(op.f("ix_tasks_user_id_created_at"), table_name="tasks")
    op.drop_table("tasks")
