"""Migration round trip on its own temporary SQLite file (Goal 2).

Plain `def` tests: migrations/env.py calls asyncio.run(), which can't run inside pytest's loop.
CHECK constraints are verified here and by the raw-insert tests, because `alembic check`
doesn't compare them.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

EXPECTED = {
    "tasks": {
        "pk": "pk_tasks",
        "checks": {
            "ck_tasks_module",
            "ck_tasks_kind",
            "ck_tasks_status",
            "ck_tasks_no_ticket_booking",
        },
        "indexes": {"ix_tasks_user_id_created_at"},
        "fks": set(),
    },
    "task_events": {
        "pk": "pk_task_events",
        "checks": {
            "ck_task_events_from_status",
            "ck_task_events_to_status",
            "ck_task_events_reason_code",
        },
        "indexes": set(),
        "fks": {"fk_task_events_task_id_tasks"},
    },
}


def _config(db_path: Path) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["database_url"] = f"sqlite+aiosqlite:///{db_path}"
    return cfg


def test_upgrade_downgrade_upgrade(tmp_path):
    db_path = tmp_path / "m.db"
    cfg = _config(db_path)
    sync_engine = create_engine(f"sqlite:///{db_path}")
    try:
        command.upgrade(cfg, "head")
        inspector = inspect(sync_engine)
        assert set(EXPECTED) <= set(inspector.get_table_names())
        for table, expected in EXPECTED.items():
            assert inspector.get_pk_constraint(table)["name"] == expected["pk"]
            assert {c["name"] for c in inspector.get_check_constraints(table)} == expected["checks"]
            assert {i["name"] for i in inspector.get_indexes(table)} == expected["indexes"]
            assert {f["name"] for f in inspector.get_foreign_keys(table)} == expected["fks"]

        command.downgrade(cfg, "base")
        remaining = set(inspect(sync_engine).get_table_names())
        assert not (set(EXPECTED) & remaining)

        command.upgrade(cfg, "head")
        assert set(EXPECTED) <= set(inspect(sync_engine).get_table_names())
    finally:
        sync_engine.dispose()
