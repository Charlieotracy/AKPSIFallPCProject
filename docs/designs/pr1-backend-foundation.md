# PR #1: Backend Foundation and Task Lifecycle

*   **Author:** krishivjthakkar
*   **Status:** Approved
*   **Date:** 2026-11-19

--------------------------------------------------------------------------------

## Overview

This is the first pull request for the Python backend of the Jev UW scheduling assistant. The team plan (`jev-uw-team-plan.md` at the repository root, which defines the modules, roles and terms used here) puts a FastAPI backend at the center of the system. The Chrome extension sends it chat messages and adapter results. The backend stores each request as a **task** and moves that task through a fixed set of statuses until it is done, fails, is handed to the user, or is cancelled.

PR #1 builds only the part every later feature depends on:

*   a FastAPI application that starts and answers `GET /health`;
*   a database schema, created by a migration, for tasks and their status history;
*   the task state machine: the list of statuses, which moves between them are allowed, and the code that enforces those rules;
*   two read-only routes, `GET /tasks` and `GET /tasks/{id}`, that return only the current user's tasks;
*   tests and a CI workflow; tests run against SQLite locally, and against both PostgreSQL and SQLite in CI.

Nothing in PR #1 talks to an LLM, to Jev, to a UW website, or to the browser extension.

## The Problem

**Nothing exists yet for the other components to plug into.** `main` contains only Rohan's Java Watch Service. Two teammates have finished backend code on unmerged branches: Ari's Jev wrapper (`ari/jev-wrapper-and-evals`) and Jeffrey's parameter extraction (`jeffrey/chat-to-task`). Both say they are waiting for P2's FastAPI app and data models. Arya's side panel needs a backend to call. Every route in the plan (`/chat`, `/tasks`, `/watches`, `/decide`, `/confirm`, WebSocket) needs a task model, a database and a way to identify the user first.

**The task lifecycle is where the safety rules live.** The plan has hard rules that models cannot override:

*   a booking needs the user's explicit confirmation;
*   tickets are never bought;
*   sensitive UHS (University Health Services, campus health appointments) details are never stored.

If tasks can jump between any statuses, those rules depend on every caller remembering them. If the allowed moves are written down as data and checked in one function, the rules are enforced in one place and tested once. For example, no ordinary code path can put a task into `executing` (booking in progress).

**The plan's status list has gaps and does not match how the system will work.** It has no status for "waiting for the user to sign in" and no cancellation. It stores statuses (`received`, `routed`) that last only part of a single request. It doesn't say which task kinds may use which statuses. Those gaps were resolved during brainstorming (`concepts_brief.md`, Section 1A). This PR turns them into code.

**Proposed solution:** a small FastAPI service with:

*   async SQLAlchemy and an Alembic migration;
*   a 12-status state machine stored as a table of allowed moves, each of which can be limited to certain task kinds;
*   a `transition()` function that checks the move, refuses guarded moves, and uses a version number so two concurrent updates can't overwrite each other;
*   a status-history table that records only statuses, versions and reason codes, never user content;
*   read-only task routes behind a temporary identity that only works on a developer's machine or in tests.

## Goals

PR #1 is done when all of these hold. Each one can be checked with a command or a test.

1.  **The app runs locally.** One documented command starts it, and `GET /health` returns HTTP 200.
2.  **The migration is reproducible.** `alembic upgrade head` creates the `tasks` and `task_events` tables on an empty SQLite or PostgreSQL database, and `alembic check` reports no differences from the models on PostgreSQL.
3.  **Tasks persist.** A task created through the service layer can be read back after the session that wrote it is closed.
4.  **Only allowed moves succeed.**
    *   Every move in the transition table succeeds for each kind it allows.
    *   Moves outside the table are rejected.
    *   An allowed move is rejected for a kind it doesn't allow.
5.  **`executing` can't be reached through `transition()`.** The `awaiting_confirm → executing` move is refused even for a `book` task.
6.  **Concurrent updates don't overwrite each other.** If two updates start from the same version, the first succeeds and the second raises `VersionConflict`. The test is deterministic and passes on SQLite and PostgreSQL.
7.  **The status history contains no user content.** Every status change writes exactly one `task_events` row in the same transaction. The row holds only statuses, the version and a reason code from a closed list.
8.  **The creation rules hold** (the full list is under "`transition()` contract"). Creating a UHS task with any `params` key other than `category`, `earliest` or `latest` is rejected with an error. Creating a `tickets` task of kind `book` is rejected.
9.  **The read routes are scoped to the current user.**
    *   `GET /tasks` and `GET /tasks/{id}` return only the current user's tasks.
    *   Another user's task returns 404.
    *   A request with no identity returns 401.
10. **The temporary identity fails closed.** The app refuses to start if the dev identity is enabled and `APP_ENV` isn't `local` or `test`. A missing `APP_ENV` counts as `prod`.
11. **CI runs on every backend change.** A GitHub Actions workflow runs `ruff`, the test suite against PostgreSQL, `alembic upgrade head` and `alembic check`.
12. **The author can explain every decision.** The spec has a decisions log with one line of reasoning per choice.

## Non-Goals

These are deliberately left out of PR #1. Each belongs to a later PR or to a teammate.

*   **No LLM or Jev calls.** `/chat` and `/decide` come later and will call Jeffrey's `extract()` and Ari's `decide()`. This PR doesn't import or copy either.
*   **No browser or UW-site interaction.** That means no WebSocket, no adapters, no candidates storage and no booking execution.
*   **No confirm tokens and no guarded execution operation.** The guarded move is only refused here. The operation that is allowed to make that move comes in the confirmation PR.
*   **No real authentication.** Invite codes and user accounts come in a later PR. The dev identity is a stand-in that can't run in production.
*   **No `POST /tasks` or any route that changes data.** Tasks are created only through the service layer, by tests and the dev seed script. Real task creation will come from `/chat`.
*   **No full per-module `params` validation.** Only the creation rules in Goal 8. Jeffrey's typed schemas replace them when they merge.
*   **No watchers, watch triggers, notifications or Watch Service integration.** The `watching` status exists, but nothing in PR #1 records watch firings or talks to the Java service. The backend uses its own database, separate from the Watch Service's.
*   **No JSON Schema export, TypeScript type generation or deployment.**
*   **No changes to teammates' branches or files.** This PR may later need a small merge with Jeffrey's provisional `backend/pyproject.toml`. That is expected and is handled at merge time, not by editing his branch.

## Open Questions

None block PR #1. They are recorded here so later sessions don't ask them again.

*   **Is a UHS `category` itself sensitive?** For example, should `mental_health` be stored and returned by `GET /tasks`? This needs a decision with Jeffrey before UHS tasks are created by real users. PR #1 allows it because it is in the team plan's allowed keys.
*   **How are watch firings recorded?** A firing doesn't change the task's status, so it doesn't fit the status-history table as designed. This is decided in the watchers PR.
*   **What is the canonical home for the shared `Module`, `Kind` and `TaskStatus` types?** Jeffrey's schemas define `Module` and `Kind` too. PR #1 defines its own copies in the backend's domain package. One home is chosen when his schemas merge.

## Critical User Journeys (CUJs)

The users of PR #1 are developers on the team, not students. These journeys describe what a teammate can do after it merges.

### CUJ 1: A teammate runs the backend and checks it is alive

*   **Given:**
    *   a fresh clone of `main`;
    *   Python 3.12 and `uv` installed;
    *   `APP_ENV=local` and `DEV_IDENTITY_ENABLED=true` set as documented in `backend/README.md`.
*   **When:** they install dependencies, run the migration, and start the app with the documented commands.
*   **Then:**
    *   `GET /health` returns 200;
    *   a local SQLite file holds the `tasks` and `task_events` tables;
    *   no network calls are made to any external service.

### CUJ 2: A frontend developer sees seeded tasks through the API

*   **Given:** the app is running locally with the dev identity, and the seed script has created a few tasks for the dev user and one for a different user.
*   **When:** they call `GET /tasks`, then `GET /tasks/{id}` for one of the dev user's tasks and for the other user's task.
*   **Then:**
    *   the list contains only the dev user's tasks, newest first;
    *   the single-task request returns the task with its status and version;
    *   the request for the other user's task returns 404.

### CUJ 3: A backend developer moves a task and is stopped from breaking the rules

*   **Given:** a `search` task in `ready`, created through the service layer.
*   **When:** the developer calls `transition()` to move it to `searching`, then to `done`. Separately, they try to move a `search` task from `searching` to `candidates`, and a `book` task from `awaiting_confirm` to `executing`.
*   **Then:**
    *   the first two moves succeed, raise the version each time, and each write one `task_events` row;
    *   the `candidates` move is rejected because the edge is limited to `book` tasks;
    *   the `executing` move is refused because the edge is guarded.

    No task row or event changes when a move is rejected.

### CUJ 4: Someone accidentally deploys with the dev identity on

*   **Given:** `DEV_IDENTITY_ENABLED=true`, and `APP_ENV` either unset or set to `prod`.
*   **When:** the app starts.
*   **Then:** startup fails with an error saying the dev identity is only allowed when `APP_ENV` is `local` or `test`. No route ever answers.

### CUJ 5: CI catches a migration that doesn't match the models

*   **Given:** a pull request that changes a model column without adding a migration.
*   **When:** the backend CI workflow runs.
*   **Then:** `alembic check` against PostgreSQL fails and the check is marked failed on the pull request.

## Technical Plan (Architecture)

### Where PR #1 sits

```text
                 (later PRs)                          PR #1
  extension ──► /chat, /ws, /decide, /confirm ──┐
                                                │
  developer / tests ──► GET /health             │
                        GET /tasks              ▼
                        GET /tasks/{id} ──► app/api ──► app/services/tasks.py ──► app/db ──► SQLite (local)
                                                │              │                            PostgreSQL (CI, prod)
                                     get_current_user          │
                                     (dev identity only)       ▼
                                                        app/domain/tasks.py
                                                        (statuses, transition table,
                                                         check_transition: pure, no I/O)
```

Each layer has one job, and calls only go one way, from left to right:

| Layer | Package | Job | Knows about |
| --- | --- | --- | --- |
| API | `app/api/` | HTTP: parse the request, find the current user, call a service, turn the result or error into a response. | services, schemas |
| Response schemas | `app/schemas/` | Pydantic models that define the JSON the API returns. These become the shared contracts later (JSON Schema → TypeScript in a later PR). | domain enums |
| Services | `app/services/tasks.py` | The only code that creates or changes tasks. It runs the creation rules, the compare-and-swap update and the event insert. | domain, db |
| Domain | `app/domain/tasks.py` | Plain Python: the enums, the transition table, and `check_transition()`. No database and no FastAPI, so it is tested without either. | nothing |
| Database | `app/db/` | SQLAlchemy tables, the UTC time type, the engine and sessions. | nothing above it |

Later PRs add new callers on the left (`/chat`, the WebSocket handler, the watchers). They use the same service functions. Nothing on the left may write to the tables directly.

### Statuses

| Status | Meaning | Kinds | Terminal | Who moves it out (eventually) |
| --- | --- | --- | --- | --- |
| `needs_info` | Required parameters are missing; waiting for the user's reply. | all | no | `/chat` (P4 logic) |
| `ready` | Parameters are complete; nothing has started. | all | no | `/chat`, task runner |
| `searching` | An adapter or API search is running. | search, book | no | adapter results (P6) |
| `awaiting_login` | A search found the user signed out; waiting for them to sign in. | search, book | no | extension (P6) |
| `candidates` | Options are stored and shown; the user hasn't picked one. | book | no | user via side panel |
| `awaiting_confirm` | The user picked an option; waiting for explicit confirmation. | book | no | `/confirm` (later PR) |
| `executing` | A booking is in progress. Reachable only through the future guarded operation. | book | no | adapter result |
| `watching` | A watch is active. A firing does not change this status. | watch | no | user, watchers |
| `done` | Finished: search results stored, booking succeeded, or watch ended. | all | yes | — |
| `failed` | Ended by a definite error. A retry is a new task. | all | yes | — |
| `handed_off` | The assistant can't finish and gives the user the next step (e.g. call UHS, or check a booking whose outcome is unknown). | all | yes | — |
| `cancelled` | The user or the system stopped the task. | all | yes | — |

A task is created in `needs_info` or `ready`. No other starting status is allowed.

### Transition table (source of truth)

This table is stored as data in `app/domain/tasks.py`. "Kinds" lists the task kinds that may use the edge, and a blank means any kind. "Guarded" edges are refused by `transition()`.

| From | To | Kinds | Guarded |
| --- | --- | --- | --- |
| `needs_info` | `ready` | | |
| `ready` | `needs_info` | | |
| `ready` | `searching` | search, book | |
| `ready` | `watching` | watch | |
| `searching` | `done` | search | |
| `searching` | `candidates` | book | |
| `searching` | `awaiting_login` | search, book | |
| `awaiting_login` | `searching` | search, book | |
| `candidates` | `awaiting_confirm` | book | |
| `awaiting_confirm` | `candidates` | book | |
| `awaiting_confirm` | `executing` | book | **yes** |
| `executing` | `done` | book | |
| `watching` | `done` | watch | |
| every non-terminal status | `failed` | | |
| every non-terminal status | `handed_off` | | |
| every non-terminal status except `executing` | `cancelled` | | |

The last three rows are expanded into explicit edges when the module loads, so the stored table is a flat list of `(from, to, kinds, guarded)` entries that tests can iterate over.

Worked examples:

*   **Search:** `ready → searching → done`.
*   **Book:**
    *   happy path: `ready → searching → candidates → awaiting_confirm → [guarded] executing → done`;
    *   the user changes their mind at confirmation: `awaiting_confirm → candidates`;
    *   the booking outcome is unknown: `executing → handed_off` (reason `outcome_unknown`).
*   **Watch:** `ready → watching → done | cancelled`. Booking a seat that opened is a separate `book` task.
*   **Sign-in:** `searching → awaiting_login → searching`. Signing in never leads into the booking states. The future guarded execution operation also checks sign-in and leaves the task in `awaiting_confirm` if the user isn't signed in.

### Reason codes

`reason_code` is a closed `StrEnum`, and every event must use one of its values. It is the only explanation an event carries. It is never built from an exception message, user text or an f-string. The PR #1 list:

`created`, `info_provided`, `missing_info`, `search_started`, `login_required`, `login_completed`, `results_ready`, `candidates_ready`, `candidate_selected`, `candidate_changed`, `booking_succeeded`, `booking_failed`, `outcome_unknown`, `not_bookable_online`, `watch_started`, `watch_ended`, `user_cancelled`, `internal_error`.

PR #1 does not tie reason codes to specific edges. A code from the list is accepted on any allowed edge. Tying them to edges would add a second table to keep in sync for little safety gain, because reason codes describe a change and grant no permissions. Adding a value later needs a migration, since the database CHECK constraint lists the values.

### Data model

**`tasks`**

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| `id` | `Uuid` | no | Primary key. Generated by the app with `uuid4()`. Native `uuid` on PostgreSQL, `CHAR(32)` on SQLite. |
| `user_id` | `String(64)` | no | Opaque user identifier. No foreign key: there is no users table until the auth PR. |
| `module` | `String(16)` | no | CHECK in (`courses`, `uhs`, `cbtf`, `tickets`). |
| `kind` | `String(16)` | no | CHECK in (`search`, `book`, `watch`). |
| `params` | `JSON` (`JSONB` on PostgreSQL) | no | A JSON object with JSON-native values. No database default: `create_task` always writes it (`{}` when none is given). Validated only by the creation rules below. |
| `status` | `String(32)` | no | CHECK in the 12 statuses. |
| `version` | `Integer` | no | Starts at 1. Every successful transition adds 1. |
| `created_at` | `UTCDateTime` | no | Set by the app. |
| `updated_at` | `UTCDateTime` | no | Set by the app on create and on every transition. |

Constraints and indexes:

*   **No ticket purchases:** a CHECK `NOT (module = 'tickets' AND kind = 'book')`. This puts the "never buy tickets" rule in the database as well as in the service.
*   **List queries:** an index on `(user_id, created_at)` for `GET /tasks`.

**`task_events`** (status history)

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| `task_id` | `Uuid` | no | Foreign key to `tasks.id`. |
| `version` | `Integer` | no | The task version this event produced. |
| `from_status` | `String(32)` | yes | Null only for the creation event. Otherwise CHECK in the 12 statuses. |
| `to_status` | `String(32)` | no | CHECK in the 12 statuses. |
| `reason_code` | `String(32)` | no | CHECK in the reason-code list. |
| `created_at` | `UTCDateTime` | no | Set by the app. |

*   **Primary key:** `(task_id, version)`. This orders a task's events without relying on timestamps, which can tie. It also makes a second write for the same version fail at the database. It doubles as the index for "events of a task", so no separate index is needed.
*   **No user content:** there is no free-text column. Statuses and reason codes come from closed lists that are checked by the database.

**Storing enum-like values.** Values are stored as plain strings with named CHECK constraints, built from the Python enums. Native PostgreSQL `ENUM` types are not used. Changing a value list then means one migration that drops and recreates a constraint, rather than an `ALTER TYPE`, and the migration is the same on SQLite and PostgreSQL. All constraints and indexes get names from a SQLAlchemy naming convention, so Alembic can find them later.

**`UTCDateTime`.** A small SQLAlchemy type wrapper around `DateTime(timezone=True)`. When writing, it refuses a datetime with no time zone (a programming error) and converts the value to UTC. When reading, it attaches UTC if the database returned a value without a time zone, which SQLite does. Without it, tests would see different values on SQLite and PostgreSQL.

### The state machine in code

Two functions, deliberately split:

1.  **`check_transition(kind, from_status, to_status)`** in `app/domain/tasks.py`. Pure: no database, no I/O.
    *   If no edge exists for this `(from, to)`, it raises `IllegalTransition`.
    *   If the edge exists but `kind` isn't in its allowed kinds, it raises `IllegalTransition`.
    *   If the edge is guarded, it raises `GuardedTransition`.
    *   Otherwise it returns nothing.

    Tests go over the whole table and every kind without touching a database.

2.  **`transition(session, *, user_id, task_id, expected_version, to_status, reason)`** in `app/services/tasks.py`. The step-by-step contract is below.

`transition()` is the only supported way to change a task's status. `apply_transition` is a separate function only so the race test can call it with a stale copy; application code never calls it directly.

There is no `start_execution()` and no way to bypass the guard in PR #1. The confirmation PR will add the one function allowed to make the guarded move, and that function will need a valid confirm token.

### `transition()` contract

```text
transition(session, user_id, task_id, expected_version, to_status, reason) -> Task

  1. task = load_task(session, user_id, task_id)
        no row with this id AND user_id  -> raise TaskNotFound      (API: 404)
  2. if task.version != expected_version  -> raise VersionConflict   (API: 409, later PRs)
  3. apply_transition(session, task, to_status, reason):
       a. reason is not a ReasonCode      -> raise TypeError (before any database call)
       b. old_status, old_version = task.status, task.version   (never read task fields after d)
       c. check_transition(task.kind, old_status, to_status)
                                          -> IllegalTransition / GuardedTransition
       d. UPDATE tasks
            SET status = to_status, version = old_version + 1, updated_at = now_utc
            WHERE id = task.id AND user_id = task.user_id
              AND status = old_status AND version = old_version
          rows changed == 0               -> raise VersionConflict
       e. INSERT task_events (task_id, version = old_version + 1,
                              from_status = old_status, to_status, reason_code, created_at)
       f. flush, refresh the task from the database, and return it
  4. return the task returned by step 3
```

Rules:

*   **The caller owns the transaction.** It wraps the call in `async with session.begin():`. `transition()` never commits or rolls back. If any step raises, the caller's transaction rolls back, and neither the status change nor the event is saved. That is what makes "one status change, one event" hold.
*   **Steps 1 and 3 are separate functions on purpose** (`load_task`, `apply_transition`). That way a test can load a task, let another session change it, and then call `apply_transition` with the stale copy. That proves the compare-and-swap in step 3b catches a real interleaving, not only the early check in step 2.
*   **Failures are never retried automatically.** A `VersionConflict` means the caller decided based on an out-of-date task. The caller reloads the task and decides again; a later API client gets a 409 and does the same.
*   **`expected_version` comes from the caller,** not from `transition()` reading the row itself. The version is the caller's statement of which task state its decision was based on. If `transition()` read the current version and used that, it would quietly turn a decision based on old information into a write.
*   **User scoping happens first.** The task is loaded with both `id` and `user_id`, so another user's task is "not found" (404), never "conflict" (409). `user_id` stays in the `UPDATE` as a second check.

`create_task(session, *, user_id, module, kind, params, initial_status)` follows the same transaction rule. It:

*   checks that `initial_status` is `needs_info` or `ready`;
*   runs the creation rules;
*   inserts the task at version 1 and a `created` event with a null `from_status`.

The creation rules raise `InvalidTaskParams`. Invalid input is rejected, never silently stripped:

*   `module == "uhs"` and `params` has any key other than `category`, `earliest` or `latest`;
*   `module == "uhs"` and a non-null `category` fails `re.fullmatch(r"[a-z_]{1,32}", value)`, or a non-null `earliest`/`latest` is not a string that `datetime.fromisoformat` parses with a UTC offset (each key may be absent or `null`, matching Jeffrey's optional `UhsParams`);
*   `json.dumps(params, allow_nan=False)` fails (values must be JSON-native; datetimes are ISO-8601 strings with an offset);
*   `module == "tickets"` and `kind == "book"`;
*   `params` is not a JSON object.

Errors live in `app/domain/errors.py`: `TaskNotFound`, `IllegalTransition`, `GuardedTransition`, `VersionConflict`, `InvalidTaskParams`. In PR #1 the API only maps `TaskNotFound` to 404, because the read routes can't raise the others. The 409 mapping for `VersionConflict` is added with the first route that changes data.

### Identity and settings

Settings are read from environment variables (and an optional, git-ignored `.env` file) with `pydantic-settings`:

| Setting | Values | Default | Rule |
| --- | --- | --- | --- |
| `APP_ENV` | `local`, `test`, `prod` | `prod` | A missing value is treated as production. |
| `DEV_IDENTITY_ENABLED` | bool | `false` | `true` is only allowed when `APP_ENV` is `local` or `test`. Otherwise settings validation fails and the app doesn't start. |
| `DATABASE_URL` | SQLAlchemy async URL | none | When unset, `local` and `test` use `sqlite+aiosqlite:///./jev_uw_local.db`, and `prod` refuses to start. |

`get_current_user` in `app/api/deps.py` is the single identity seam:

*   dev identity enabled: returns `CurrentUser(id="dev-user")`;
*   otherwise: raises HTTP 401.

There is no header or query parameter that picks a different user. Tests reach "another user" by creating that user's tasks directly through the service. The auth PR replaces the body of `get_current_user` and keeps its signature.

`create_app(settings=None)` builds the app. Tests pass their own `Settings`, and production reads them from the environment.

### Database sessions (async rules)

*   **Engine:** one async engine per app, created at startup in FastAPI's `lifespan` hook and disposed at shutdown.
*   **Sessions:** `async_sessionmaker(expire_on_commit=False)`. After a commit, loaded objects keep their values instead of reloading lazily, which in async code fails with a confusing error.
*   **One session per request:** created by the `get_session` dependency and passed explicitly to service functions. Services never create sessions.
*   **No ORM relationships:** `task_events` are queried directly when needed. This removes a class of async lazy-loading errors without needing `lazy="raise"`.
*   **Read routes** run their queries in the request session. They don't need an explicit write transaction.

### Migrations

*   **Alembic** with the async template (`env.py` runs migrations through the async engine).
*   **`render_as_batch=True`,** because SQLite can't alter tables in place.
*   **The first migration is written by hand,** not autogenerated, so every line can be read and explained. `alembic check` on PostgreSQL proves that tables, columns, types, indexes and foreign keys match the models. It does not compare CHECK constraints, so `test_migrations` and the raw-insert tests cover those.
*   **`DATABASE_URL`** is read from the same `Settings`, so the app and migrations always target the same database.
*   **Tests build the schema with `alembic upgrade head`**, not `metadata.create_all()`, so every test run also tests the migration.

### Testing approach

*   **One suite, two databases.** `DATABASE_URL` is for the app and migrations. The test suite uses `TEST_DATABASE_URL`, or a fresh temporary SQLite file when that is unset or empty; it never uses `DATABASE_URL` or `.env`. Never point `TEST_DATABASE_URL` at a database you want to keep: tests delete all rows after each test. Locally the suite runs on SQLite; CI runs it on both PostgreSQL and SQLite. It uses a temporary file rather than an in-memory SQLite database, because each in-memory connection is a separate, empty database and the concurrency test needs two connections to see the same rows.
*   **Schema setup and cleanup:** the migration runs once per test session. Rows are deleted after each test.
*   **Pure domain tests** (`check_transition`) run without a database.
*   **The race test:** session A loads a task in a transaction that commits, so A holds no lock. Session B then transitions and commits the task, and A calls `apply_transition` with its stale copy and must get `VersionConflict`. It runs on both databases. **Rule for test authors:** every test must close its sessions (use `async with`). A test that leaves a transaction open makes the cleanup `DELETE` wait forever on PostgreSQL, and CI hangs instead of failing.

### Packaging and CI

*   **`backend/pyproject.toml` lines up key by key with Jeffrey's provisional file:**
    *   setuptools build backend, project name `jev-uw-backend`, `requires-python >= 3.12`;
    *   `[tool.setuptools.packages.find] include = ["app*"]`;
    *   dev tools under `[project.optional-dependencies] dev`;
    *   pytest `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `pythonpath = ["."]`;
    *   ruff line length 100, `py312`.

    It does not add `anthropic`, prompt files or any agent dependency.
*   **All pytest settings live in `pyproject.toml`, and `backend/pytest.ini` must not exist.** When that file exists, pytest ignores the `pyproject.toml` settings and the async tests break. This was reproduced on a trial merge of the two teammate branches. The PR description tells Ari.
*   **`uv.lock` is committed,** and CI installs with `uv sync --locked --extra dev`.
*   **`.github/workflows/backend.yml`** is modeled on `watch-service.yml`:
    *   **Triggers:** path filters on `backend/**` and the workflow file, with `working-directory: backend`.
    *   **Database:** a `postgres:16` service container.
    *   **Steps:** `ruff check` → `alembic upgrade head` → `alembic check` → `pytest` (PostgreSQL) → `pytest` (SQLite), all in one job.

### Invariants

Each invariant is proved by at least one test, named in the Verification Plan.

| ID | Invariant |
| --- | --- |
| INV-1 | Every task creation and every successful status change writes exactly one `task_events` row, in the same transaction as the task change. |
| INV-2 | `transition()` never makes a guarded move. `executing` is unreachable in PR #1. |
| INV-3 | A move succeeds only if `(from, to)` is in the table and the task's kind is allowed on that edge. |
| INV-4 | A write based on an out-of-date version never succeeds. It raises `VersionConflict` and changes nothing. |
| INV-5 | `task_events` holds only statuses, versions, closed-list reason codes and timestamps. |
| INV-6 | A UHS task's `params` has no key other than `category`, `earliest` or `latest`; each is `null`, a short lowercase identifier (`category`) or an offset-aware ISO-8601 datetime (`earliest`, `latest`); and no `tickets` task has kind `book`. |
| INV-7 | A user can never read another user's task. The response is 404, the same as for a task that doesn't exist. |
| INV-8 | The dev identity can't be active unless `APP_ENV` is `local` or `test`. |
| INV-9 | Terminal statuses have no outgoing edges, and every non-terminal status has an edge to a terminal status. |

### Differences from the team plan

| Team plan | PR #1 | Reason |
| --- | --- | --- |
| Statuses `received`, `routed` | Not stored | They happen inside one `/chat` request, before a task exists. |
| Status `triggered` (watch) | Not a status | A watch keeps watching after it fires. A booking is a separate task. |
| No sign-in status | `awaiting_login` added | The plan says a task "waits" for sign-in but had no status for it. |
| No cancellation | `cancelled` added (not from `executing`) | Users must be able to stop a task, but not one with a click in flight. |
| `failed` | Terminal for all kinds; a retry is a new task | Avoids retrying with stale candidates. |
| `handed_off` | Also covers "booking outcome unknown" (`outcome_unknown`) | An uncertain booking must never be retried automatically. |
| Any status may go anywhere the flow needs | Edges limited by kind; `executing` guarded | Safety rules are enforced in one function. |
| `Task.params: dict` | Stored as JSON with two creation rules | Full per-module validation arrives with Jeffrey's schemas. |
| `id: str` | UUID, sent as a string in JSON | Type-checked in Python and the database; looks the same to clients. |
| `/tasks` route (unspecified) | Read-only `GET` in PR #1 | Tasks are created by `/chat`, not by clients directly. |

### Decisions log

| Decision | Reason |
| --- | --- |
| Async SQLAlchemy and async routes | WebSocket handlers must be async and will write to the database. Jeffrey's `extract()` is async. One model is easier than mixing. |
| Compare-and-swap on `version`, not `SELECT … FOR UPDATE` | It works the same on SQLite and PostgreSQL. It holds no locks while the caller decides. A losing writer learns that its information was out of date. |
| Caller passes `expected_version` | The write is tied to the state the decision was based on. |
| No automatic retry on conflict | Retrying would apply an old decision to a new state. |
| One transition table with optional kinds | Three per-kind tables would have to be kept in sync. A table without kinds would let search tasks reach booking statuses. |
| Guarded edge refused, no stub | The safety property can be tested now, and the real caller arrives with tokens. |
| Transition rules never read history | The rules depend only on the current status, the target and the kind, so they are easy to test and to reason about. |
| `failed` terminal | It matches the plan and avoids stale retries. |
| Strings + CHECK, not native enums | Status lists will change, and the migrations stay simple and the same on both databases. |
| `(task_id, version)` as the event primary key | Gives ordering without timestamps and stops two events claiming the same version. Because the key starts with `task_id`, it also serves lookups by task. The separate `task_id` index proposed in the brief was dropped by the author as redundant. |
| Opaque string `user_id`, no FK | Real auth isn't designed yet, and the plan uses a string. |
| Creation rules inline in `create_task`, plus a DB CHECK for tickets | The hard rules hold now without copying Jeffrey's code or adding a placeholder validator layer. |
| Fixed dev user, no user-switch header | A switch header would be an identity bypass that someone could forget to remove. |
| Hand-written first migration with literal value lists | It is readable and explainable. `alembic check` covers columns, types and indexes, and tests cover the CHECK constraints. Literals mean editing an enum never changes a past migration. |
| No ORM relationships | Avoids async lazy-loading errors, and nothing needs relationships yet. |
| Temp-file SQLite in tests | The concurrency test needs two connections that see the same data. |
| `GET /tasks` returns `{"items": [...]}` | Pagination fields can be added later without breaking clients. |
| `GET /health` doesn't touch the database | It checks only that the process is up. A database check can be added with deployment. |

## Alternatives Considered

Each alternative below was raised during the brainstorm (`concepts_brief.md`, Sections 1A and 4) or in the design discussion before it. The rejections are the author's decisions.

### Alternative A: One transition graph with no kind restrictions

*   **Pros:** The simplest table, with no `kinds` column. Callers decide which edges make sense for their task.
*   **Cons:** `transition()` would let a `search` task reach `candidates` or `awaiting_confirm`, and a `book` task enter `watching`. The booking path would depend on every caller remembering the rules.
*   **Reason for Rejection:** Rejected by author: it lets search tasks reach booking statuses. An optional kinds restriction costs one column and one check.

### Alternative B: A separate state machine for each task kind

*   **Pros:** Each kind's lifecycle can be read on its own, and no edge needs a kinds list.
*   **Cons:** Three tables share most of their edges (`failed`, `handed_off`, `cancelled`, `needs_info ⇄ ready`). A change to a shared edge has to be made three times, and the tables can drift apart.
*   **Reason for Rejection:** Rejected by author: three tables to keep in sync, for no safety gain over one table with kind restrictions.

### Alternative C: Store `received`, `routed` and `triggered` as statuses (as in the team plan)

*   **Pros:** Matches the plan word for word, and teammates already know the names.
*   **Cons:** `received` and `routed` happen inside one `/chat` request before a task exists, so storing them adds edges and tests for statuses that last milliseconds. `triggered` would end or interrupt a watch, but users want a watch to keep alerting after it fires.
*   **Reason for Rejection:** Rejected by author: the two request-time statuses describe work in progress inside one request, not task state. A firing watch stays `watching`, and a booking is a separate task.

### Alternative D: Let a watch move into the booking statuses (`watching → candidates`)

*   **Pros:** One task covers "tell me when a seat opens" through "enroll me".
*   **Cons:** The watch's lifecycle and the booking's lifecycle get mixed together. A booking failure would end the watch, and a recurring watch couldn't fire twice.
*   **Reason for Rejection:** Rejected by author: it mixes two lifecycles. Booking after a firing is a new `book` task with its own confirmation.

### Alternative E: Resume edges that check history (return to "where the task came from")

*   **Pros:** `awaiting_login` could return to whichever status it came from, and `failed` could return to `candidates` only after a booking failure.
*   **Cons:** `transition()` would have to read `task_events` to decide whether a move is allowed. The rules would then depend on history, not just on the current status, the target and the kind, which makes them harder to test and to explain.
*   **Reason for Rejection:** Rejected by author: transition checks must not read past events. The edges that needed history were removed instead. `awaiting_login` returns only to `searching`, and `failed` is terminal.

### Alternative F: Loose resume edges, relying on the future confirm-token guard

*   **Pros:** No extra rules; the token check at execution is the only booking safety.
*   **Cons:** `awaiting_login → awaiting_confirm` would let a task signed out during search jump to confirmation without a chosen candidate. Booking safety would rest on a single check that doesn't exist yet.
*   **Reason for Rejection:** Rejected by author: it weakens confirmation, and the leaking edges can simply be removed.

### Alternative G: Retry from `failed` (`failed → ready`, `failed → candidates`)

*   **Pros:** One task records the whole history of a request, including its retries.
*   **Cons:** A retried booking could act on stale candidates. A retry rule needs extra conditions (which failures may retry, how many times), and `failed` stops meaning "finished".
*   **Reason for Rejection:** Rejected by author: a retry creates a new task that checks availability again. `failed` stays terminal, which also matches the team plan.

### Alternative H: Row locking with `SELECT … FOR UPDATE` instead of compare-and-swap

*   **Pros:** The second writer waits instead of failing. Familiar from transactional systems.
*   **Cons:** SQLite has no `FOR UPDATE`, so local tests and production would behave differently. A lock held while the caller decides blocks other writers. The waiting writer then applies its old decision to a new state unless it re-checks anyway.
*   **Reason for Rejection:** Rejected by author: compare-and-swap on `version` works the same on both databases, holds no locks, and tells a losing writer that its information is out of date.

### Alternative I: Retry automatically on `VersionConflict`

*   **Pros:** Fewer errors seen by callers.
*   **Cons:** The retry would apply a decision made on old information to a new state. An example is cancelling a task that has already moved on.
*   **Reason for Rejection:** Rejected by author: the caller reloads the task and decides again, and an API client gets a 409.

### Alternative J: Synchronous SQLAlchemy and `def` routes

*   **Pros:** Fewer async pitfalls (lazy loading, session lifetime, test event loops). FastAPI runs `def` routes in a thread pool automatically. The traffic is small.
*   **Cons:** WebSocket handlers must be async and will write to the database, and Jeffrey's `extract()` is async. A mixed codebase would need thread-pool bridges in both directions.
*   **Reason for Rejection:** Rejected by author: one async model throughout is simpler than mixing. The async pitfalls are handled by the session rules (`expire_on_commit=False`, no relationships, one explicit session per request).

### Alternative K: `POST /tasks` in PR #1 behind the dev identity

*   **Pros:** A frontend developer could create tasks through the API right away.
*   **Cons:** The real product never has clients create tasks directly; tasks come from `/chat` after routing and extraction. A public create route would also go around extraction. For example, a client could create a `tickets` `book` task, or UHS params with free text. PR #1 has no full params validation to stop that.
*   **Reason for Rejection:** Rejected by author: tasks are created only through the service layer (tests and a dev seed script). Real creation arrives with `/chat`.

### Alternative L: Wait for Jeffrey's schemas before protecting UHS params

*   **Pros:** One source of truth for params, and no temporary rules.
*   **Cons:** Until his branch merges, nothing would stop UHS free text from being stored, which breaks a hard constraint.
*   **Reason for Rejection:** Rejected by author: two inline checks in `create_task` (allowed UHS keys; no ticket booking) keep the rule now, without copying his code or adding a placeholder validator layer.

### Alternative M: Native PostgreSQL `ENUM` types for status, module, kind and reason

*   **Pros:** The database enforces the value list, and the values show up in schema tools.
*   **Cons:** Every change to a list is an `ALTER TYPE` migration that SQLite doesn't have, and it can make `alembic check` report spurious differences. The status list has already changed once.
*   **Reason for Rejection:** Rejected by author: strings with named CHECK constraints enforce the same lists and migrate the same way on both databases.

### Alternative N: `Uuid` type for `user_id`

*   **Pros:** Matches task IDs and is type-checked.
*   **Cons:** The identity design (invite codes, later auth) isn't done. The plan uses a string, and the dev identity is `"dev-user"`.
*   **Reason for Rejection:** Rejected by author: an opaque `String(64)` doesn't constrain the future auth design.

### Alternative O: Build test tables with `metadata.create_all()` and use in-memory SQLite

*   **Pros:** Faster test setup, and no migration step in tests.
*   **Cons:** `create_all()` doesn't test the migration, so a broken migration could pass CI. Each in-memory SQLite connection is a separate, empty database, so the two-session conflict test couldn't see shared rows.
*   **Reason for Rejection:** Rejected by author: tests use `alembic upgrade head` on a temporary-file SQLite database locally and on PostgreSQL in CI.

### Alternative P: Keep ORM relationships with `lazy="raise"`

*   **Pros:** `task.events` is convenient to read, and `lazy="raise"` turns hidden lazy loads into clear errors.
*   **Cons:** It is one more async rule to learn and enforce, and nothing in PR #1 needs to navigate from a task to its events.
*   **Reason for Rejection:** Rejected by author: there are no relationships. Events are queried directly when a later PR needs them.

### Alternative Q: A `start_execution()` stub in PR #1

*   **Pros:** The final API shape is visible early.
*   **Cons:** A stub that can make the guarded move without a token is a bypass waiting to be called. A stub that always refuses adds nothing the guard doesn't already do.
*   **Reason for Rejection:** Rejected by author: the guarded edge is refused and tested now. The only function allowed to make it arrives with confirm tokens.

--------------------------------------------------------------------------------

## Non-Functional Requirements

*   **Security and privacy:**
    *   **Secrets:** no secrets are committed. `.env` is git-ignored, and `backend/.env.example` holds only placeholder values.
    *   **Fail-closed identity:** the dev identity can't start outside `local` or `test` (INV-8), and a missing `APP_ENV` counts as `prod`.
    *   **No content in the history:** `task_events` holds no user content (INV-5).
    *   **UHS params:** a UHS task's params are limited to three keys (INV-6).
    *   **Logging:** PR #1 adds no log statements that include `params`, request bodies or query strings. The engine is created with `hide_parameters=True`, so SQLAlchemy error messages don't include bound values such as `params`. `Settings` uses `hide_input_in_errors=True`, so a startup validation error never echoes `DATABASE_URL` (which holds a password); a test checks this.
    *   **Cross-user access:** another user's task looks the same as a missing one (INV-7).
*   **Performance:** not a concern at this size (one team, tens of tasks). The only index added is the one `GET /tasks` needs. The list is capped at 50 items.
*   **Rollout and rollback:** PR #1 isn't deployed. To roll back, revert the PR. The migration has a `downgrade()` that drops both tables, tested on SQLite.
*   **Merging with teammates' branches:** expect small, mechanical conflicts in three files when Jeffrey's and Ari's branches merge:
    *   `.gitignore`, which all three branches edit;
    *   `backend/pyproject.toml`, which Jeffrey's branch creates with mostly the same keys;
    *   `backend/pytest.ini`, which Ari must delete.
    *   `backend/uv.lock`, which is regenerated with `uv lock` after `pyproject.toml` is merged, never merged by hand.

    `backend/app/__init__.py` is empty in all three branches, so it doesn't conflict.

### Additional Resources

*   `jev-uw-team-plan.md`: architecture, task statuses, hard rules, repo layout.
*   `concepts_brief.md`: brainstorm working notes. This document supersedes it, and it is not committed.
*   `services/watch-service/README.md` and `.github/workflows/watch-service.yml`: conventions the backend CI mirrors.
*   Unmerged branches, read only: `jeffrey/chat-to-task` (`backend/pyproject.toml`, `app/agent/orchestrator/schemas.py`) and `ari/jev-wrapper-and-evals` (`backend/pytest.ini`, `app/agent/jev/decide.py`).

### Future Improvements

*   **Params validation:** replace the inline creation rules with Jeffrey's typed per-module schemas from `app/schemas/`, and choose one home for `Module`, `Kind` and `TaskStatus`.
*   **Confirm tokens:** add a guarded execution operation whose tokens are bound to `(task_id, version)`, so any status change invalidates outstanding tokens.
*   **Conflict mapping:** map `VersionConflict` to 409 when the first route that changes data is added.
*   **Watch firings:** decide how they are recorded, since they are not status changes.
*   **Possible tightening:** tie reason codes to edges, if misleading history becomes a problem in practice.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

No file outside this list is created, changed or deleted. Paths are relative to the repository root. No file on a teammate's branch is edited. Every file under `backend/` is new on `main`. The brainstorm and review working files (`concepts_brief.md`, `design_draft.md`, `implementation_readiness_report.md`, `goldfish_review_report.md`) are not committed.

### Implementation Phases

Work proceeds in five phases. Each phase leaves the code buildable and its tests passing, and ends with a walkthrough of its code and tests before the next phase starts. File numbers refer to the list below.

| Phase | Files | Gate (run from `backend/`) |
| --- | --- | --- |
| 1. Packaging and settings | 1, 3-7, 11, 24 (env-clearing fixture only), 28 (all but the two `create_app` cases) | `uv run ruff check .` and `uv run pytest tests/test_config.py` |
| 2. Domain | 12, 13, 25 | `uv run pytest tests/test_domain_transitions.py` |
| 3. Database and migration | 8-10, 14-16, 30 | `uv run pytest tests/test_migrations.py` and `APP_ENV=local uv run alembic upgrade head` on SQLite |
| 4. Services | 17, 24 (database fixtures and `make_task`), 26, 27 | `uv run pytest tests/test_task_service.py tests/test_concurrency.py` on SQLite |
| 5. API, scripts, CI and docs | 2, 18-23, 24 (`make_client`, `client`), 28 (the two `create_app` cases), 29, 31 | The full suite on SQLite and PostgreSQL, `alembic upgrade head` and `alembic check` on PostgreSQL, and the manual check |

### Target Files to Create/Modify

#### 1. `.gitignore` (Modify)

*   **Type / Scope:** Repository configuration.
*   **Proposed Changes:**
    *   **Additions:** a `# Python backend` block with `.venv/`, `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.ruff_cache/`, `*.egg-info/`, `.env`, `*.db`, `*.sqlite`, `*.sqlite3`, `backend/reports/`.
    *   **Untouched:** the existing lines.
*   **Why:** Keeps local databases, virtual environments and `.env` secrets out of git. This supports the "no secrets in source control" rule.

#### 2. `.github/workflows/backend.yml` (Create)

*   **Type / Scope:** CI workflow.
*   **Proposed Changes:**
    *   **Triggers:** `push` and `pull_request`, with path filters `backend/**` and `.github/workflows/backend.yml`.
    *   **Name:** `name: backend`.
    *   **Job:** one `test` job on `ubuntu-latest`, with `defaults.run.working-directory: backend`.
    *   **Database:** a `postgres:16` service with user, password and database set to test-only literals (`jev`/`jev`/`jev_uw_test`), a `pg_isready` health check and `ports: ["5432:5432"]`.
    *   **Environment:**
        *   `APP_ENV=test`;
        *   `DATABASE_URL=postgresql+asyncpg://jev:jev@localhost:5432/jev_uw_test`;
        *   `TEST_DATABASE_URL` set to the same value.
    *   **Steps, in order:**
        1.  `actions/checkout@v4`;
        2.  `astral-sh/setup-uv@v6`, with `python-version: "3.12"` and `enable-cache: true`;
        3.  `uv sync --locked --extra dev`;
        4.  `uv run ruff check .`;
        5.  `uv run alembic upgrade head`;
        6.  `uv run alembic check`;
        7.  `uv run pytest -q --junitxml=reports/pytest-postgres.xml` (PostgreSQL);
        8.  `TEST_DATABASE_URL= uv run pytest -q --junitxml=reports/pytest-sqlite.xml` (SQLite);
        9.  `actions/upload-artifact@v4` with `if: failure()`, `name: backend-test-reports` and `path: backend/reports/`.
*   **Why:** Goals 2, 6 and 11. It follows `watch-service.yml`'s conventions: path filters, `working-directory`, `checkout@v4`, and uploading reports on failure. The Postgres credentials exist only inside the CI container and are not secrets.

#### 3. `backend/pyproject.toml` (Create)

*   **Type / Scope:** Build and tool configuration.
*   **Proposed Changes:**
    *   **`[build-system]`:** setuptools `>=68`.
    *   **`[project]`:** `name = "jev-uw-backend"`, `version = "0.1.0"`, `requires-python = ">=3.12"`.
    *   **Dependencies:**
        *   `fastapi>=0.115`
        *   `uvicorn[standard]>=0.30`
        *   `sqlalchemy[asyncio]>=2.0.30`
        *   `alembic>=1.13`
        *   `aiosqlite>=0.20`
        *   `asyncpg>=0.29`
        *   `pydantic>=2.7,<3`
        *   `pydantic-settings>=2.3`
    *   **`[project.optional-dependencies] dev`:**
        *   `pytest>=8`
        *   `pytest-asyncio>=0.24` (the first version with `asyncio_default_fixture_loop_scope`; Jeffrey's file should raise its minimum too)
        *   `httpx>=0.27`
        *   `ruff`
    *   **`[tool.setuptools.packages.find]`:** `include = ["app*"]`.
    *   **`[tool.pytest.ini_options]`:**
        *   `asyncio_mode = "auto"`
        *   `asyncio_default_fixture_loop_scope = "function"`
        *   `testpaths = ["tests"]`
        *   `pythonpath = ["."]`
    *   **`[tool.ruff]`:** `line-length = 100`, `target-version = "py312"`, default rule set.
    *   **Not included:** `anthropic`, prompt package data and agent dependencies.
*   **Why:** It uses the same build backend, package include, dev-dependency layout, pytest asyncio settings and ruff settings as Jeffrey's provisional file. When his branch merges, `dependencies` and `dev` are combined, and his `tzdata`, `[tool.setuptools.package-data]` and `live` marker are kept. It adds no ruff rules beyond the defaults his file uses.

#### 4. `backend/uv.lock` (Create, generated)

*   **Type / Scope:** Lock file.
*   **Proposed Changes:** Generated by `uv lock`, never edited by hand.
*   **Why:** CI installs the exact same versions (`uv sync --locked`).

#### 5. `backend/.python-version` (Create)

*   **Type / Scope:** Tool configuration.
*   **Proposed Changes:** The single line `3.12`.
*   **Why:** `uv` picks Python 3.12 locally, whatever the machine's default Python is.

#### 6. `backend/.env.example` (Create)

*   **Type / Scope:** Documentation by example.
*   **Proposed Changes:** `APP_ENV=local`, `DEV_IDENTITY_ENABLED=true`, and a commented-out `DATABASE_URL=` line.
*   **Why:** Shows which settings exist. It is copied to `.env`, which is git-ignored.

#### 7. `backend/README.md` (Create)

*   **Type / Scope:** Documentation.
*   **Proposed Changes:** Sections:
    *   **What exists:** PR #1 scope, and a link to the design doc.
    *   **Run locally:**
        *   `uv sync --extra dev`
        *   `cp .env.example .env`
        *   `uv run alembic upgrade head`
        *   `uv run uvicorn app.main:create_app --factory --reload`
        *   `curl localhost:8000/health`
    *   **Seed data:** `uv run python scripts/seed_dev.py`.
    *   **Run tests:** SQLite by default. For PostgreSQL, set `TEST_DATABASE_URL`.
    *   **Configuration:** the settings table.
    *   **Warning:** never set `APP_ENV` to `local` or `test` in a deployed environment. Those are the only values that allow the dev identity.
    *   **Note for teammates:** don't add `backend/pytest.ini`. pytest would then ignore `[tool.pytest.ini_options]`, and the async tests would break.
*   **Why:** CUJ 1. Follows the shape of `services/watch-service/README.md`.

#### 8. `backend/alembic.ini` (Create)

*   **Type / Scope:** Migration configuration.
*   **Proposed Changes:**
    *   `script_location = %(here)s/migrations`, so it works from any working directory;
    *   `file_template = %%(rev)s_%%(slug)s`. New revisions are created with `alembic revision --rev-id NNNN -m "<slug>"`;
    *   no `sqlalchemy.url`, which `env.py` reads from `Settings` instead;
    *   standard logging sections.
*   **Why:** It keeps no database URL in the file, so the app and migrations always use the same `DATABASE_URL`, unless tests override it. `app` is importable from `env.py` because `uv sync` installs the project in editable mode.

#### 9. `backend/migrations/env.py` (Create)

*   **Type / Scope:** Alembic environment.
*   **Proposed Changes:**
    *   **Async template:** `asyncio.run()` around an async engine, with `connection.run_sync(do_run_migrations)`.
    *   **Database URL:** `url = config.attributes.get("database_url") or Settings().resolved_database_url`. `Settings()` is built only when no test override is given.
    *   **Models:** `target_metadata = app.db.models.Base.metadata`.
    *   **Batch mode:** `render_as_batch=True` for every database. It is required on SQLite and harmless on PostgreSQL.
    *   **Logging:** `fileConfig(config.config_file_name, disable_existing_loggers=False)` runs only when no test override is set, so tests keep their logging.
    *   **Type checks:** `compare_type=True`, so `alembic check` catches type differences.
*   **Why:** `render_as_batch`, the URL from `Settings` or the test override, and `compare_type`.

#### 10. `backend/migrations/script.py.mako` and `backend/migrations/versions/0001_create_tasks.py` (Create)

*   **Type / Scope:** Migration template and first migration, hand-written.
*   **Proposed Changes:**
    *   **Template:** the standard Alembic template.
    *   **`upgrade()`:**
        *   creates `tasks` with the columns, the named CHECK constraints (module, kind, status, no ticket booking), the `JSON().with_variant(JSONB, "postgresql")` params column (no database default), and the index `ix_tasks_user_id_created_at`;
        *   creates `task_events` with primary key `(task_id, version)`, a foreign key to `tasks.id`, and CHECK constraints on `from_status` (null or one of the 12 statuses), `to_status` and `reason_code`.
    *   **Value lists:** hard-coded as literals. The migration never imports the enums, so editing an enum can never change a past migration. A test (§26) checks that every enum value is accepted by the database, which catches drift.
    *   **Names:** every constraint and index uses its full name from the table in §15, through `op.f(...)`.
    *   **Revision:** `revision = "0001"`, `down_revision = None`.
    *   **Time columns:** `UTCDateTime` imported from `app/db/types.py`.
    *   **`downgrade()`:** drops `task_events`, then `tasks`.
*   **Why:** Goal 2. Hand-written so every line can be explained. `alembic check` covers tables, columns, types, indexes and foreign keys. It does not compare CHECK constraints, so `test_migrations` and the raw-insert tests cover those.

#### 11. `backend/app/__init__.py` (Create, empty) and `backend/app/config.py` (Create)

*   **Type / Scope:** Package marker; settings.
*   **Proposed Changes:**
    *   **`Settings(BaseSettings)`:**
        *   `app_env: Literal["local", "test", "prod"] = "prod"`;
        *   `dev_identity_enabled: bool = False`;
        *   `database_url: str | None = None`.

        Settings are read from the environment and from `.env`: `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`. The `.env` path is relative to the working directory, which is `backend/` for every documented command. `extra="ignore"` lets `.env` hold keys for other components.
    *   **Tests never read `.env`.** Every `Settings(...)` built in tests passes `_env_file=None`.
    *   **Startup check (model validator):** if `dev_identity_enabled` is true and `app_env` is `prod`, raise `ValueError("DEV_IDENTITY_ENABLED is only allowed when APP_ENV is local or test")`.
    *   **`resolved_database_url` property:**
        *   returns `database_url` if it is set and not empty (an empty value counts as unset);
        *   otherwise returns `sqlite+aiosqlite:///./jev_uw_local.db` when `app_env` is `local` or `test`;
        *   otherwise raises `ValueError("DATABASE_URL is required when APP_ENV is prod")`.
*   **Why:** INV-8, CUJ 4. Defaulting to `prod` means a deploy that forgets the setting fails closed.

#### 12. `backend/app/domain/__init__.py` (Create, empty) and `backend/app/domain/tasks.py` (Create)

*   **Type / Scope:** Pure domain module, with no I/O imports.
*   **Proposed Changes:**
    *   **Enums (`StrEnum`):**
        *   `Module` (4 values);
        *   `Kind` (3 values);
        *   `TaskStatus` (12 values);
        *   `ReasonCode` (18 values, as listed in the Technical Plan).
    *   **Status sets:**
        *   `TERMINAL_STATUSES = {done, failed, handed_off, cancelled}`;
        *   `INITIAL_STATUSES = {needs_info, ready}`.
    *   **`Edge`:** a frozen dataclass with `from_status`, `to_status`, `kinds: frozenset[Kind] | None` (`None` means any kind) and `guarded: bool = False`.
    *   **`TRANSITIONS: tuple[Edge, ...]`:**
        *   the 13 explicit edges from the table;
        *   plus edges built when the module loads: `→ failed` and `→ handed_off` from every non-terminal status, and `→ cancelled` from every non-terminal status except `executing`.

        A duplicate `(from, to)` pair raises an error at import time.
    *   **`_EDGE_INDEX`:** a dictionary keyed by `(from, to)`.
    *   **`check_transition(kind, from_status, to_status) -> None`:** follows the Technical Plan. Error messages contain only enum values.
*   **Why:** INV-2, INV-3, INV-9. Because the module is pure, the whole table is tested without a database.

#### 13. `backend/app/domain/errors.py` (Create)

*   **Type / Scope:** Domain exceptions.
*   **Proposed Changes:**
    *   **Base class:** `TaskError(Exception)`.
    *   **Subclasses:**
        *   `TaskNotFound`
        *   `IllegalTransition`
        *   `GuardedTransition`
        *   `VersionConflict`
        *   `InvalidTaskParams`
    *   **Messages:** contain only IDs, enum values and key names, never `params` values.
*   **Why:** Distinct errors let callers and tests tell "not found", "not allowed", "guarded", "out of date" and "invalid params" apart.

#### 14. `backend/app/db/__init__.py` (Create, empty) and `backend/app/db/types.py` (Create)

*   **Type / Scope:** SQLAlchemy custom type.
*   **Proposed Changes:**
    *   **`UTCDateTime(TypeDecorator)`:** `impl = DateTime(timezone=True)`, `cache_ok = True`.
    *   **When writing:** a datetime with no time zone raises `ValueError`; otherwise the value is converted to UTC.
    *   **When reading:** a value with no time zone gets UTC attached; otherwise it is converted to UTC.
    *   **`utcnow()`:** a helper that returns `datetime.now(UTC)`.
*   **Why:** It gives timezone-aware UTC datetimes on both databases. The migration imports it from here.

#### 15. `backend/app/db/models.py` (Create)

*   **Type / Scope:** SQLAlchemy 2.0 declarative models.
*   **Proposed Changes:**
    *   **`Base(DeclarativeBase)`:** its `MetaData` uses the naming convention `ix_%(column_0_label)s`, `ck_%(table_name)s_%(constraint_name)s`, `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`, `pk_%(table_name)s`.
    *   **`TaskRow`:** maps to `tasks` with the columns, constraints and index from the Technical Plan. String columns use `Mapped[str]`. CHECK constraints are built from the enum values.
    *   **`TaskEventRow`:** maps to `task_events`.
    *   **No `relationship()`** anywhere.
    *   **`params`** has no Python or server default. `create_task` always sets it.
    *   **Final names.** Every `CheckConstraint` sets `name=` to the short suffix, and the naming convention adds the prefix. The index is an explicit `Index("ix_tasks_user_id_created_at", "user_id", "created_at")`. The full set:

        | Table | Names |
        | --- | --- |
        | `tasks` | `pk_tasks`, `ck_tasks_module`, `ck_tasks_kind`, `ck_tasks_status`, `ck_tasks_no_ticket_booking`, `ix_tasks_user_id_created_at` |
        | `task_events` | `pk_task_events`, `fk_task_events_task_id_tasks`, `ck_task_events_from_status`, `ck_task_events_to_status`, `ck_task_events_reason_code` |
*   **Why:** It is the model side of the migration, and `alembic check` compares the two.

#### 16. `backend/app/db/session.py` (Create)

*   **Type / Scope:** Engine and session wiring.
*   **Proposed Changes:**
    *   **`make_engine(url) -> AsyncEngine`:** calls `create_async_engine(url, hide_parameters=True)`. For SQLite URLs it also passes `connect_args={"timeout": 5}` and registers a `connect` event listener on `engine.sync_engine` (async engines don't take pool events directly) that runs `PRAGMA foreign_keys=ON`, so SQLite enforces foreign keys the way PostgreSQL does.
    *   **`make_sessionmaker(engine)`:** returns `async_sessionmaker(engine, expire_on_commit=False)`.
    *   **`get_session(request) -> AsyncIterator[AsyncSession]`:** a FastAPI dependency that opens a session from `request.app.state.sessionmaker` and closes it after the response.
*   **Why:** `expire_on_commit=False`, one session per request, and foreign keys on SQLite, all in one place.

#### 17. `backend/app/services/__init__.py` (Create, empty) and `backend/app/services/tasks.py` (Create)

*   **Type / Scope:** Task service: the only application code that writes tasks.
*   **Proposed Changes:**
    *   **`create_task(session, *, user_id, module, kind, params, initial_status) -> TaskRow`:**
        1.  Validate `initial_status ∈ INITIAL_STATUSES`; otherwise raise `IllegalTransition`.
        2.  `params = {} if params is None else params`. Run `_check_creation_rules(module, kind, params)`, which raises `InvalidTaskParams` when:
            *   `params` is not a dict;
            *   `json.dumps(params, allow_nan=False)` fails (values must be JSON-native; datetimes are ISO-8601 strings);
            *   `module == "uhs"` and there is a key other than `category`, `earliest` or `latest` (only key names go in the message);
            *   `module == "uhs"` and a key that is present and not `null` has a bad value: `category` must satisfy `re.fullmatch(r"[a-z_]{1,32}", value)`; `earliest`/`latest` must be strings that `datetime.fromisoformat` parses with a non-null `tzinfo`. Absent or `null` keys are accepted;
            *   `module == "tickets"` and `kind == "book"`.

            The exact UHS category list is enforced when Jeffrey's schemas merge.
        3.  Add a `TaskRow` with `id=uuid4()`, version 1 and `created_at = updated_at = utcnow()`, then `flush()`, so the task row is inserted before its event.
        4.  Insert a `TaskEventRow` with version 1, a null `from_status`, `to_status = initial_status` and reason `created`.
        5.  Flush and return the row. It does not commit.
    *   **`load_task(session, *, user_id, task_id) -> TaskRow`:** selects by `id` and `user_id`. If no row is found, it raises `TaskNotFound`.
    *   **`apply_transition(session, task, *, to_status, reason) -> TaskRow`:**
        1.  If `reason` is not a `ReasonCode`, raise `TypeError` before touching the database.
        2.  `old_status, old_version = task.status, task.version`. After the UPDATE, nothing reads `task.status` or `task.version`.
        3.  `check_transition(task.kind, old_status, to_status)`.
        4.  `result = await session.execute(update(TaskRow).where(TaskRow.id == task.id, TaskRow.user_id == task.user_id, TaskRow.status == old_status, TaskRow.version == old_version).values(status=to_status, version=old_version + 1, updated_at=utcnow()).execution_options(synchronize_session=False))`. `synchronize_session=False` stops SQLAlchemy from changing the in-memory task before the event is written.
        5.  If `result.rowcount == 0`, raise `VersionConflict`.
        6.  Add the event with `version=old_version + 1`, `from_status=old_status`, `to_status` and `reason_code=reason`.
        7.  `await session.flush()`, `await session.refresh(task)`, and return the task.
    *   **`transition(session, *, user_id, task_id, expected_version, to_status, reason) -> TaskRow`:** calls `load_task`; if the version doesn't match, raises `VersionConflict`; then calls `apply_transition`.
    *   **`list_tasks(session, *, user_id, limit=50) -> list[TaskRow]`:** ordered by `created_at` descending, then `id` descending.
    *   **Not in this module:** commits, logging of `params`, and session creation.
*   **Why:** INV-1, INV-4, INV-6. It is the single place where task rules are applied.

#### 18. `backend/app/schemas/__init__.py` (Create, empty) and `backend/app/schemas/tasks.py` (Create)

*   **Type / Scope:** Pydantic response models (the future shared contracts).
*   **Proposed Changes:**
    *   **`TaskOut(BaseModel)`:** fields `id: UUID`, `module: Module`, `kind: Kind`, `status: TaskStatus`, `version: int`, `params: dict[str, Any]`, `created_at: datetime`, `updated_at: datetime`; `model_config = ConfigDict(from_attributes=True)`. `user_id` is not exposed.
    *   **`TaskList(BaseModel)`:** `items: list[TaskOut]`.
*   **Why:** It defines the JSON contract now, and these models are what a later PR exports to JSON Schema and TypeScript.

#### 19. `backend/app/api/__init__.py` (Create, empty) and `backend/app/api/deps.py` (Create)

*   **Type / Scope:** FastAPI dependencies.
*   **Proposed Changes:**
    *   **`DEV_USER_ID = "dev-user"`.**
    *   **`CurrentUser`:** a frozen dataclass with `id: str`.
    *   **`get_current_user(request) -> CurrentUser`:** returns `CurrentUser(DEV_USER_ID)` if `request.app.state.settings.dev_identity_enabled` is true. Otherwise it raises `HTTPException(401, detail="not authenticated")` with the header `WWW-Authenticate: Bearer`.
*   **Why:** INV-8 and Goal 9. This is the single identity seam that the auth PR replaces.

#### 20. `backend/app/api/health.py` (Create)

*   **Type / Scope:** Route.
*   **Proposed Changes:** `GET /health` returns `{"status": "ok"}` with HTTP 200. It needs no identity and doesn't touch the database.
*   **Why:** Goal 1.

#### 21. `backend/app/api/tasks.py` (Create)

*   **Type / Scope:** Routes.
*   **Proposed Changes:**
    *   **`GET /tasks`:** returns `TaskList` with up to 50 of the current user's tasks, newest first.
    *   **`GET /tasks/{task_id}`:**
        *   `task_id` is typed `UUID`, so FastAPI answers 422 when it isn't a valid UUID;
        *   on success it returns `TaskOut`;
        *   if `TaskNotFound` is raised, it returns 404 `{"detail": "task not found"}`. The 404 is raised from the route, so no global exception handler is added.
    *   **Dependencies:** both routes depend on `get_current_user` and `get_session`.
*   **Why:** Goal 9, INV-7.

#### 22. `backend/app/main.py` (Create)

*   **Type / Scope:** App factory.
*   **Proposed Changes:** `create_app(settings: Settings | None = None) -> FastAPI`:
    1.  `settings = settings or Settings()`, then `database_url = settings.resolved_database_url`. Either can raise, so `create_app` fails before it returns an app: a forbidden dev identity fails in the first, and a missing `DATABASE_URL` in `prod` fails in the second.
    2.  A `lifespan` hook creates the engine and sessionmaker from the already-resolved `database_url`, stores them on `app.state`, and disposes the engine on shutdown.
    3.  It stores `settings` on `app.state`.
    4.  It includes the health and tasks routers.

    There is **no module-level `app = create_app()`**. Importing `app.main` in tests must not read the developer's environment, so uvicorn runs it with `--factory`.
*   **Why:** CUJ 1 and CUJ 4. Tests inject their own `Settings`.

#### 23. `backend/scripts/seed_dev.py` (Create)

*   **Type / Scope:** Developer script, not part of the app package.
*   **Proposed Changes:**
    1.  It reads `Settings()` and exits with an error unless `app_env == "local"`.
    2.  It opens a session with `make_engine` and `make_sessionmaker`.
    3.  In one transaction, it calls `create_task` and `transition`. It does not write rows directly.
    4.  It creates these tasks for `dev-user`:
        *   a `courses`/`search` task in `ready`;
        *   a `courses`/`search` task moved `ready → searching → done`;
        *   a `cbtf`/`book` task moved to `awaiting_confirm`;
        *   a `courses`/`watch` task moved to `watching`;
        *   a `uhs`/`book` task in `needs_info` with `params={"category": "primary_care"}`.
    5.  It creates one `courses`/`search` task for `other-user`.
    6.  It prints the IDs it created and disposes the engine.

    Details:
    *   Every moved task starts in `ready`.
    *   Reason codes:
        *   to `searching`: `search_started`
        *   to `done` (search): `results_ready`
        *   to `candidates`: `candidates_ready`
        *   to `awaiting_confirm`: `candidate_selected`
        *   to `watching`: `watch_started`
    *   If any task already exists, the script refuses to run and prints how to start fresh: delete `jev_uw_local.db` and run `alembic upgrade head`.
*   **Why:** CUJ 2. Its only UHS value is `category=primary_care`, with no free text, and it goes through the same service rules as everything else.

#### 24. `backend/tests/conftest.py` (Create)

*   **Type / Scope:** Test fixtures. The file grows by phase: Phase 1 adds only the autouse environment fixture; Phase 4 adds the database fixtures and `make_task`; Phase 5 adds `make_client` and `client`. Application modules are imported inside the fixtures that use them, never at the top of the file, so conftest imports cleanly before those modules exist.
*   **Proposed Changes:**
    *   **`TEST_DATABASE_URL`:** read once with `os.environ.get` when conftest is imported, before any fixture runs.
    *   **Autouse environment fixture:** `monkeypatch.delenv(name, raising=False)` for `APP_ENV`, `DEV_IDENTITY_ENABLED` and `DATABASE_URL`, so no test sees the developer's shell settings.
    *   **`database_url` (session scope, plain `def`):**
        *   uses `TEST_DATABASE_URL` if it is set and not empty;
        *   otherwise uses `sqlite+aiosqlite:///<tmp_path_factory>/test.db`;
        *   runs `alembic.command.upgrade(cfg, "head")` once, where `cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))` and `cfg.attributes["database_url"] = url`. Because it is plain `def`, it runs outside pytest's event loop, which `env.py`'s `asyncio.run()` requires.
    *   **`engine` (function scope, async):** `make_engine(database_url)`. After each test it runs `DELETE FROM task_events` and then `DELETE FROM tasks` in its own transaction, and disposes the engine. Rule for test authors: every test must close its own sessions (`async with`); an open transaction makes this `DELETE` hang on PostgreSQL.
    *   **`sessionmaker`:** `make_sessionmaker(engine)`.
    *   **`test_settings`:** `Settings(_env_file=None, app_env="test", dev_identity_enabled=True, database_url=database_url)`.
    *   **`make_client` (fixture):** returns an async context manager `make_client(settings)`. It does:
        1.  `app = create_app(settings)`;
        2.  `async with app.router.lifespan_context(app)`;
        3.  yields `httpx.AsyncClient(transport=ASGITransport(app), base_url="http://test")`.

        `client` is `make_client(test_settings)`.
    *   **`make_task` (fixture):** returns an async function `make_task(*, user_id="dev-user", module="courses", kind="search", params=None, initial_status="ready", created_at=None) -> TaskRow`. It calls `create_task` in its own committed transaction. If `created_at` is given, it then sets `created_at` and `updated_at` with a Core update and refreshes the returned row, which lets ordering tests use distinct times.
*   **Why:** One suite runs on both databases, and the migration is applied on every run.

#### 25. `backend/tests/test_domain_transitions.py` (Create)

*   **Type / Scope:** Pure unit tests, with no database.
*   **Proposed Changes:**
    *   **Allowed edges:** for every `Edge`, every allowed kind (or all three kinds when `kinds` is `None`), `check_transition` passes, except for guarded edges.
    *   **Wrong kind:** for every edge with a `kinds` list, each kind outside the list raises `IllegalTransition`.
    *   **Pairs outside the table:** every `(from, to)` pair of statuses that isn't in the table raises `IllegalTransition` for all kinds. This is an exhaustive 12×12 loop.
    *   **Guarded edge:** `awaiting_confirm → executing` for `book` raises `GuardedTransition`.
    *   **Terminal statuses:** they have no outgoing edges.
    *   **Exits:** every non-terminal status has an edge to `failed` and to `handed_off`. Every non-terminal status except `executing` has an edge to `cancelled`.
    *   **No edge from `awaiting_login` into the booking statuses:** none to `awaiting_confirm`, `candidates` or `executing`.
    *   **Kind spot-checks from the transition table (the first two are named in CUJ 3):**
        *   `search`: `searching → candidates` is rejected;
        *   `book`: `ready → watching` is rejected;
        *   `watch`: `ready → searching` is rejected.
*   **Why:** INV-2, INV-3, INV-9. It covers Goals 4 and 5.

#### 26. `backend/tests/test_task_service.py` (Create)

*   **Type / Scope:** Service tests against the database. Raw inserts use Core `insert(TaskRow.__table__)` or `insert(TaskEventRow.__table__)` and expect `sqlalchemy.exc.IntegrityError`.
*   **Proposed Changes:**
    *   **Persistence:**
        *   create, then read back in a new session; all fields match;
        *   `created_at` comes back with a UTC time zone on both databases.
    *   **Creation event:** a `created` event exists with version 1 and a null `from_status`.
    *   **Initial status:** a status outside `needs_info`/`ready` raises `IllegalTransition`.
    *   **Creation rules:**
        *   UHS params with a `reason` key raise `InvalidTaskParams` and write no rows;
        *   UHS params `{"category": "primary_care", "earliest": "2026-12-01T09:00:00-06:00"}` are accepted;
        *   a UHS `category` containing spaces (for example `"I feel anxious"`) is rejected, and so is `"primary_care\n"`;
        *   a free-text UHS `earliest` (for example `"after my appointment about my anxiety"`) is rejected;
        *   a naive ISO string without an offset (`"2026-12-01T09:00"`) is rejected;
        *   `{"category": null, "earliest": null, "latest": null}` is accepted;
        *   a `datetime` object, and `float("nan")`, as params values are rejected;
        *   non-dict params are rejected;
        *   `module="tickets"` with `kind="book"` is rejected by the service;
        *   the same row inserted raw is rejected by `ck_tasks_no_ticket_booking`.
    *   **Every CHECK constraint rejects a bad value:** one parametrized raw-insert test, with one case per constraint (`ck_tasks_module`, `ck_tasks_kind`, `ck_tasks_status`, `ck_tasks_no_ticket_booking`, `ck_task_events_from_status`, `ck_task_events_to_status`, `ck_task_events_reason_code`), each expecting `IntegrityError`. It runs on both databases, so it checks the hand-written migration on PostgreSQL.
    *   **Enum values the database accepts:** every `TaskStatus`, `Module`, `Kind` and `ReasonCode` value succeeds in a raw insert. This catches an enum that drifts from the migration's literal lists.
    *   **Successful transition:**
        *   the version goes up by 1;
        *   `updated_at` is greater than or equal to its previous value;
        *   exactly one new event, with the correct `from`, `to`, version and reason.
    *   **Rejected transitions** (illegal, wrong kind or guarded): the task row and the event count are unchanged after the rollback.
    *   **Atomicity (INV-1):**
        1.  Create a task (version 1).
        2.  Raw-insert a `task_events` row at `(task_id, 2)`.
        3.  `transition(expected_version=1, ...)` inside `session.begin()` raises `IntegrityError`.
        4.  After the rollback, the task is still at version 1 with its original status.
    *   **`TaskNotFound`:** raised for another user's task and for a random UUID.
    *   **Content-free events:** the `task_events` columns are exactly `{task_id, version, from_status, to_status, reason_code, created_at}`, checked by inspecting the table.
    *   **Closed reason list:** a raw insert of a reason code outside the list fails at the database.
    *   **Reason type:** passing a plain string instead of a `ReasonCode` raises `TypeError`.
*   **Why:** INV-1, INV-5, INV-6, INV-7, plus Goals 3, 7 and 8.

#### 27. `backend/tests/test_concurrency.py` (Create)

*   **Type / Scope:** Concurrency tests. All of them run on both databases.
*   **Proposed Changes:**
    *   **Stale version:**
        1.  Create a `book` task in `ready`.
        2.  Session 1 calls `transition(expected_version=1, to_status=searching, reason=search_started)` and commits.
        3.  Session 2 calls `transition(expected_version=1, to_status=cancelled, reason=user_cancelled)` and gets `VersionConflict`.
        4.  The reloaded task is at version 2 and `searching`, and has exactly two events.
    *   **Interleaved race (tests the compare-and-swap itself):**
        1.  Create a `book` task in `ready`.
        2.  In `async with sessionmaker() as a, a.begin()`: `stale = await load_task(a, ...)`. The block commits, so A holds no lock, and `stale` keeps its values because `expire_on_commit=False`.
        3.  Session B calls `transition(expected_version=1, to_status=searching, reason=search_started)` and commits.
        4.  In session A, inside a new `a.begin()`: `apply_transition(a, stale, to_status=cancelled, reason=user_cancelled)` must raise `VersionConflict`, not `IntegrityError`.
        5.  The reloaded task is at version 2 and `searching`, and has exactly two events. The version-2 event has `to_status=searching` and `reason_code=search_started`.
    *   **Duplicate event version:** a raw insert of a second event with the same `(task_id, version)` raises `IntegrityError`.
*   **Why:** INV-4. It covers Goal 6.

#### 28. `backend/tests/test_config.py` (Create)

*   **Type / Scope:** Settings tests. Every case builds `Settings(_env_file=None, ...)`. Environment variables are cleared by the autouse fixture in conftest.
*   **Proposed Changes:**
    *   **Missing `APP_ENV`:** gives `app_env == "prod"`.
    *   **Dev identity in prod:** `DEV_IDENTITY_ENABLED=true` raises a validation error when `APP_ENV` is unset, and also when it is `prod`.
    *   **Dev identity allowed:** it is accepted when `APP_ENV` is `local` or `test`.
    *   **Database URL:**
        *   `prod` without `DATABASE_URL`: `resolved_database_url` raises;
        *   `local` without it, or with `DATABASE_URL=""`: the SQLite default is used.
    *   **Startup fails closed** (Phase 5, because it needs `create_app`):
        *   `monkeypatch.chdir(tmp_path)`, so no `.env` exists, and `monkeypatch.setenv("DEV_IDENTITY_ENABLED", "true")`: `create_app()` raises before it returns an app;
        *   `create_app(Settings(_env_file=None, app_env="prod"))` with no `DATABASE_URL` also raises before it returns an app.
*   **Why:** INV-8, CUJ 4. It covers Goal 10.

#### 29. `backend/tests/test_api.py` (Create)

*   **Type / Scope:** HTTP tests through `httpx.AsyncClient`, using the `client` and `make_client` fixtures.
*   **Proposed Changes:**
    *   **`GET /health`:** 200 `{"status": "ok"}`.
    *   **`GET /tasks`:**
        *   returns only the dev user's tasks, newest first, under `items`. Tasks are created with distinct `created_at` values through `make_task`;
        *   `user_id` is not in the response;
        *   with 51 tasks, it returns exactly 50.
    *   **`GET /tasks/{id}`:**
        *   for the user's own task: 200 with the right `status` and `version`;
        *   for another user's task: 404;
        *   for a random UUID: 404;
        *   for a value that isn't a UUID: 422.
    *   **No identity:** using `make_client(Settings(_env_file=None, app_env="test", dev_identity_enabled=False, database_url=database_url))`:
        *   both task routes return 401 with detail `"not authenticated"` and the header `WWW-Authenticate: Bearer`;
        *   `/health` still returns 200.
*   **Why:** Goals 1 and 9, INV-7.

#### 30. `backend/tests/test_migrations.py` (Create)

*   **Type / Scope:** Migration round-trip test. The tests are plain `def`, not `async def`, because `env.py` calls `asyncio.run()`. They always use their own temporary SQLite file, never the shared test database.
*   **Proposed Changes:**
    1.  Build `Config` from `Path(__file__).resolve().parents[1] / "alembic.ini"` with `attributes["database_url"]` set to `sqlite+aiosqlite:///<tmp>/m.db`.
    2.  `upgrade head`.
    3.  With a sync engine (`create_engine("sqlite:///<tmp>/m.db")`) and `sqlalchemy.inspect`, check that both tables exist and that the constraint and index names exactly match the table in §15.
    4.  `downgrade base`; check that both tables are gone.
    5.  `upgrade head` again.
*   **Why:** Goal 2, and the rollback note in the Non-Functional Requirements. CHECK constraints are verified here and by the raw-insert tests, because `alembic check` doesn't compare them. The PostgreSQL migration is covered by the `alembic upgrade head` and `alembic check` steps in CI.

#### 31. `docs/designs/pr1-backend-foundation.md` (Create)

*   **Type / Scope:** Design document (this file).
*   **Proposed Changes:** Committed with the PR, with its status updated to Approved once the review is complete.
*   **Why:** Goal 12. The README links to it, and its decisions log is how the author explains each choice.

### Verification Plan

*   **Build / install:** `cd backend && uv sync --locked --extra dev` succeeds on a clean checkout.
*   **Static analysis:** `uv run ruff check .` reports no errors.
*   **Migrations:**
    *   `uv run alembic upgrade head` succeeds on an empty SQLite file and on PostgreSQL 16;
    *   `uv run alembic check` on PostgreSQL reports "No new upgrade operations detected".
*   **Tests:**
    *   `uv run pytest -q` passes on SQLite (the default);
    *   `TEST_DATABASE_URL=postgresql+asyncpg://… uv run pytest -q` passes on PostgreSQL;
    *   in CI, both runs pass in the `backend.yml` job.
*   **Invariant coverage:** each invariant maps to at least one test:

    | Invariant | Tests |
    | --- | --- |
    | INV-1 | `test_task_service` creation-event, transition-event and atomicity tests |
    | INV-2 | `test_domain_transitions` guarded test, plus the `test_task_service` guarded rollback |
    | INV-3 | `test_domain_transitions` exhaustive and kind tests |
    | INV-4 | `test_concurrency` |
    | INV-5 | `test_task_service` column and closed-reason tests |
    | INV-6 | `test_task_service` creation-rule tests and the database CHECK test |
    | INV-7 | `test_task_service` not-found tests, plus the `test_api` 404 tests |
    | INV-8 | `test_config`, plus the `test_api` 401 test |
    | INV-9 | `test_domain_transitions` terminal and exit tests |

*   **Coverage target:** no percentage target. The loops in `test_domain_transitions.py` cover every transition-table edge, and the table above maps every invariant to its tests.
*   **Manual check (CUJ 1–2):**
    1.  run the README commands;
    2.  `curl localhost:8000/health` returns 200;
    3.  run the seed script;
    4.  `curl localhost:8000/tasks` lists 5 tasks;
    5.  `curl` with the `other-user` task ID returns 404.
*   **Evidence for the PR description:** the PR description must include the pytest summary lines from both databases and the `alembic check` output.

--------------------------------------------------------------------------------

*Drafted with EGM*
