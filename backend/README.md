# Backend

Python 3.12 / FastAPI backend for the Jev UW scheduling assistant.

**Status:** PR #1 foundation only: app factory, `GET /health`, task model and state machine,
`tasks` / `task_events` tables with an Alembic migration, and read-only `GET /tasks` and
`GET /tasks/{id}` behind a local/test-only identity. No LLM, Jev, watcher, WebSocket or
booking code yet. Design and decisions:
[docs/designs/pr1-backend-foundation.md](../docs/designs/pr1-backend-foundation.md).

## Run locally

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
cd backend
uv sync --extra dev
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:create_app --factory --reload
curl localhost:8000/health          # {"status":"ok"}
```

Seed a few tasks for the dev user (refuses if any task exists):

```
uv run python scripts/seed_dev.py
curl localhost:8000/tasks
```

## Run tests

```
uv run pytest -q                    # SQLite (fresh temporary file)
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/jev_uw_test uv run pytest -q
```

Tests never use `DATABASE_URL` or `.env`. **Never point `TEST_DATABASE_URL` at a database you
want to keep:** every test deletes all rows afterwards.

## Configuration

Read from environment variables and an optional, git-ignored `backend/.env`.

| Variable | Values | Default | Rule |
| --- | --- | --- | --- |
| `APP_ENV` | `local`, `test`, `prod` | `prod` | Missing means production. |
| `DEV_IDENTITY_ENABLED` | `true` / `false` | `false` | Only allowed when `APP_ENV` is `local` or `test`; otherwise the app refuses to start. |
| `DATABASE_URL` | SQLAlchemy async URL | none | Unset or empty: `local`/`test` use `./jev_uw_local.db`; `prod` refuses to start. |

**Warning:** never set `APP_ENV` to `local` or `test` in a deployed environment. Those are the
only values that allow the dev identity.

## Notes for teammates

- Don't add `backend/pytest.ini`. pytest would ignore `[tool.pytest.ini_options]` in
  `pyproject.toml`, and the async tests would break.
- Change task statuses only through `app.services.tasks.transition()`. The allowed moves are the
  table in `app/domain/tasks.py`; `awaiting_confirm -> executing` is guarded and always refused.
- After merging changes to `pyproject.toml`, regenerate the lock with `uv lock`.

## CI

`.github/workflows/backend.yml` runs ruff, `alembic upgrade head` and `alembic check` on
PostgreSQL 16, then the test suite on PostgreSQL and on SQLite, for changes under `backend/`.
