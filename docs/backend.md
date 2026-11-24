# Backend: Overview and Contributions

This document describes the Python (FastAPI) backend of the Jev UW scheduling assistant: what exists, how the pieces fit together, and how other components connect to it. It is updated with each backend contribution; see [Changelog](#changelog).

Related documents:

- [`backend/README.md`](../backend/README.md): running the app and the tests, and the configuration reference.
- [`docs/designs/pr1-backend-foundation.md`](designs/pr1-backend-foundation.md): the approved design for the backend foundation, with its decisions log and rejected alternatives.
- [`jev-uw-team-plan.md`](../jev-uw-team-plan.md): the project plan, team roles and terminology.

## Contributors

| Contributor | Role (team plan) | Backend contributions |
| --- | --- | --- |
| Krishiv | P2: Backend core and tech lead | Backend foundation: the design and its review, the implementation described under [Current functionality](#current-functionality), and the backend CI workflow. |

## Current functionality

The backend foundation is the first backend contribution. It provides the base that later features build on. It does not yet integrate with an LLM, Jev, UW websites or the browser extension.

- **App and health check.** A FastAPI application factory, and `GET /health`, which returns `{"status": "ok"}`.
- **Database schema.** One Alembic migration creates two tables:
  - `tasks`: one row per user request;
  - `task_events`: the status history of each task.
- **Task state machine.** Twelve statuses, a table of allowed moves between them, and a service function, `transition()`, through which application code changes a task's status.
- **Read-only task routes.** `GET /tasks` and `GET /tasks/{id}` return tasks for the current user. Identity is a fixed development user that `Settings` only allows when `APP_ENV` is `local` or `test`.
- **Tests and CI.**
  - 139 tests passed locally on SQLite and on PostgreSQL 14.
  - `alembic check` reported no differences between the models and the migration on PostgreSQL 14.
  - The GitHub Actions workflow (`.github/workflows/backend.yml`) is configured to run on PostgreSQL 16 and SQLite. It has not yet run on GitHub.

### Request flow

```text
HTTP request
   │
   ▼
app/api/          routes: parse the request, resolve the user, call a service, build the response
   │   └── deps.py: get_current_user (identity)
   ▼
app/services/     creates tasks and changes their status
   │   └── app/domain/: decides whether a status change is allowed
   ▼
app/db/           table models, the UTC datetime type, the engine and sessions
   │
   ▼
SQLite (local)  /  PostgreSQL (CI and production)
```

Each layer calls only the layer below it. Routes do not write to tables directly. `app/domain/` imports nothing from FastAPI or the database, so the transition rules are tested without either.

### Task lifecycle

Each task has a module (`courses`, `uhs`, `cbtf`, `tickets`), a kind (`search`, `book`, `watch`) and a status. The allowed moves are defined in one table in `app/domain/tasks.py`:

```text
search:   ready → searching → done
book:     ready → searching → candidates → awaiting_confirm → [guarded] executing → done
watch:    ready → watching → done
sign-in:  searching → awaiting_login → searching
exits:    any non-final status → failed or handed_off; any except executing → cancelled
```

- **Kind limits.** Some moves are allowed only for certain kinds. For example, `transition()` rejects moving a `search` task to `candidates` or `awaiting_confirm`.
- **Guarded booking move.** `transition()` always refuses `awaiting_confirm → executing`. A later contribution adds a dedicated operation for this move that requires a confirm token.
- **Final statuses.** `done`, `failed`, `handed_off` and `cancelled` have no outgoing moves. A retry or a refinement is a new task.

### Concurrency

Two updates to the same task can arrive close together. For example, a user cancels while a search result is being recorded. Each task has a `version` number. The caller passes the version it last read, and the update applies only if the row still has that version:

```sql
UPDATE tasks SET ..., version = version + 1 WHERE id = ? AND version = ?
```

If no row changes, another update came first, and the service raises `VersionConflict` rather than overwriting it. Conflicts are not retried automatically: the caller reloads the task and decides again. The status update and its `task_events` row are written in the same transaction, so both are saved or neither is.

### Implemented controls

| Concern | Control | Tests |
| --- | --- | --- |
| Booking without explicit confirmation | `check_transition` refuses the guarded `awaiting_confirm → executing` move, and no other move leads into `executing`. | `test_domain_transitions.py`, `test_task_service.py` |
| Ticket purchases | `create_task` rejects tasks with module `tickets` and kind `book`. The database CHECK constraint `ck_tasks_no_ticket_booking` rejects the same rows. | `test_task_service.py` |
| Sensitive UHS details | `create_task` rejects UHS `params` with any key other than `category`, `earliest` and `latest`. A non-null `category` must be 1–32 lowercase letters or underscores. A non-null `earliest`/`latest` must be an ISO-8601 datetime with a UTC offset. These checks limit the format of values; they do not check meaning (for example, whether a category is appropriate). | `test_task_service.py` |
| User content in the status history | `task_events` has no free-text column. Statuses and reason codes are limited to closed lists by database CHECK constraints. | `test_task_service.py` |
| Cross-user access | Task queries filter by `user_id`. A request for another user's task returns 404, the same response as a missing task. | `test_api.py`, `test_task_service.py` |
| Development identity outside development | `Settings` fails validation when `DEV_IDENTITY_ENABLED` is true and `APP_ENV` is `prod` or unset. `create_app` then raises before returning an app. | `test_config.py` |
| Secrets in error messages | `Settings` uses `hide_input_in_errors=True`, so validation errors do not include setting values such as `DATABASE_URL`. The engine uses `hide_parameters=True`, so SQLAlchemy errors do not include bound values. | `test_config.py` (settings) |
| Secrets in source control | `.env` and local database files are git-ignored. `backend/.env.example` contains no credentials. | Not automated |

## Integration interfaces

These are the planned connection points. Only the read-only task routes exist today.

| Teammate | Component | Connection | Status |
| --- | --- | --- | --- |
| Jeffrey (P4) | Orchestrator, `extract()` | `/chat` calls `extract()`, then `create_task()`. The typed params schemas move to `app/schemas/` and replace the inline UHS checks in `create_task`. | Planned |
| Ari (P5) | Jev wrapper, `decide()` | `/decide` calls `decide()` in a thread pool, because it is synchronous. `Decision.raw` is not stored for UHS tasks. | Planned |
| Arya (P1) | Side panel | `GET /tasks` returns the `TaskList` shape in `app/schemas/tasks.py`. Generated TypeScript types follow in the contracts work. | Available |
| Rohan (P3) | Java Watch Service | HTTP between services; each service keeps its own database. A watch firing produces an event, and the watch task stays in `watching`. | To be designed |
| Charlie (P6) | Site adapters | Adapter results move tasks through `transition()`. Adapters do not write to the database. | Planned |

**Merging the open backend branches:**

- `ari/jev-wrapper-and-evals` adds `backend/pytest.ini`. That file must be removed when the branch merges: pytest reads it instead of `[tool.pytest.ini_options]` in `pyproject.toml`, and the async tests then fail.
- `jeffrey/chat-to-task` adds its own `backend/pyproject.toml`. When the branch is rebased:
  - its dependencies are combined with the existing ones;
  - its `tzdata` dependency, `package-data` and `live` test marker are kept;
  - `pytest-asyncio` is raised to `>=0.24`;
  - `uv lock` regenerates the lock file.

## Planned work

1. Contracts: JSON Schema export from the Pydantic models, generated TypeScript types for the extension, and a CI check that they stay in sync.
2. Users and authentication: invite codes and bearer tokens, replacing the development identity behind `get_current_user`.
3. `/chat`: route a message, extract parameters, create a task.
4. WebSocket and candidate storage.
5. `/decide` and `/confirm`, including confirm tokens and the guarded execution operation.
6. `/watches`, integrated with the Watch Service.
7. Deployment.

## Changelog

| Date | Change | Author | Summary |
| --- | --- | --- | --- |
| 2026-11-23 | Backend foundation (PR number pending) | Krishiv | FastAPI app and settings, `tasks` and `task_events` migration, 12-status state machine with kind limits and a guarded booking move, compare-and-swap transitions, read-only task routes, 139 tests (passed locally on SQLite and PostgreSQL 14), and a backend CI workflow (not yet run on GitHub). |
