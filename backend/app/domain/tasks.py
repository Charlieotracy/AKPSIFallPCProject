"""Task statuses and the transition table (pure Python: no database, no FastAPI).

The table is the single source of truth for which status changes are allowed. See the
"Transition table" section of docs/designs/pr1-backend-foundation.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .errors import GuardedTransition, IllegalTransition


class Module(StrEnum):
    COURSES = "courses"
    UHS = "uhs"
    CBTF = "cbtf"
    TICKETS = "tickets"


class Kind(StrEnum):
    SEARCH = "search"
    BOOK = "book"
    WATCH = "watch"


class TaskStatus(StrEnum):
    NEEDS_INFO = "needs_info"
    READY = "ready"
    SEARCHING = "searching"
    AWAITING_LOGIN = "awaiting_login"
    CANDIDATES = "candidates"
    AWAITING_CONFIRM = "awaiting_confirm"
    EXECUTING = "executing"
    WATCHING = "watching"
    DONE = "done"
    FAILED = "failed"
    HANDED_OFF = "handed_off"
    CANCELLED = "cancelled"


class ReasonCode(StrEnum):
    CREATED = "created"
    INFO_PROVIDED = "info_provided"
    MISSING_INFO = "missing_info"
    SEARCH_STARTED = "search_started"
    LOGIN_REQUIRED = "login_required"
    LOGIN_COMPLETED = "login_completed"
    RESULTS_READY = "results_ready"
    CANDIDATES_READY = "candidates_ready"
    CANDIDATE_SELECTED = "candidate_selected"
    CANDIDATE_CHANGED = "candidate_changed"
    BOOKING_SUCCEEDED = "booking_succeeded"
    BOOKING_FAILED = "booking_failed"
    OUTCOME_UNKNOWN = "outcome_unknown"
    NOT_BOOKABLE_ONLINE = "not_bookable_online"
    WATCH_STARTED = "watch_started"
    WATCH_ENDED = "watch_ended"
    USER_CANCELLED = "user_cancelled"
    INTERNAL_ERROR = "internal_error"


S = TaskStatus
K = Kind

TERMINAL_STATUSES = frozenset({S.DONE, S.FAILED, S.HANDED_OFF, S.CANCELLED})
INITIAL_STATUSES = frozenset({S.NEEDS_INFO, S.READY})


@dataclass(frozen=True)
class Edge:
    from_status: TaskStatus
    to_status: TaskStatus
    kinds: frozenset[Kind] | None = None  # None means any kind
    guarded: bool = False


def _kinds(*kinds: Kind) -> frozenset[Kind]:
    return frozenset(kinds)


_EXPLICIT_EDGES: tuple[Edge, ...] = (
    Edge(S.NEEDS_INFO, S.READY),
    Edge(S.READY, S.NEEDS_INFO),
    Edge(S.READY, S.SEARCHING, _kinds(K.SEARCH, K.BOOK)),
    Edge(S.READY, S.WATCHING, _kinds(K.WATCH)),
    Edge(S.SEARCHING, S.DONE, _kinds(K.SEARCH)),
    Edge(S.SEARCHING, S.CANDIDATES, _kinds(K.BOOK)),
    Edge(S.SEARCHING, S.AWAITING_LOGIN, _kinds(K.SEARCH, K.BOOK)),
    Edge(S.AWAITING_LOGIN, S.SEARCHING, _kinds(K.SEARCH, K.BOOK)),
    Edge(S.CANDIDATES, S.AWAITING_CONFIRM, _kinds(K.BOOK)),
    Edge(S.AWAITING_CONFIRM, S.CANDIDATES, _kinds(K.BOOK)),
    Edge(S.AWAITING_CONFIRM, S.EXECUTING, _kinds(K.BOOK), guarded=True),
    Edge(S.EXECUTING, S.DONE, _kinds(K.BOOK)),
    Edge(S.WATCHING, S.DONE, _kinds(K.WATCH)),
)


def _exit_edges() -> tuple[Edge, ...]:
    """Every non-terminal status can fail or be handed off; all but executing can be cancelled."""
    edges: list[Edge] = []
    for status in TaskStatus:
        if status in TERMINAL_STATUSES:
            continue
        edges.append(Edge(status, S.FAILED))
        edges.append(Edge(status, S.HANDED_OFF))
        if status is not S.EXECUTING:  # a click may already be in flight
            edges.append(Edge(status, S.CANCELLED))
    return tuple(edges)


def _build_index(edges: tuple[Edge, ...]) -> dict[tuple[TaskStatus, TaskStatus], Edge]:
    index: dict[tuple[TaskStatus, TaskStatus], Edge] = {}
    for edge in edges:
        key = (edge.from_status, edge.to_status)
        if key in index:
            raise RuntimeError(f"duplicate transition edge {key[0]} -> {key[1]}")
        index[key] = edge
    return index


TRANSITIONS: tuple[Edge, ...] = _EXPLICIT_EDGES + _exit_edges()
_EDGE_INDEX = _build_index(TRANSITIONS)


def check_transition(kind: Kind, from_status: TaskStatus, to_status: TaskStatus) -> None:
    """Raise unless a task of `kind` may move from `from_status` to `to_status`."""
    edge = _EDGE_INDEX.get((from_status, to_status))
    if edge is None:
        raise IllegalTransition(f"no transition {from_status} -> {to_status}")
    if edge.kinds is not None and kind not in edge.kinds:
        raise IllegalTransition(f"transition {from_status} -> {to_status} not allowed for {kind}")
    if edge.guarded:
        raise GuardedTransition(f"transition {from_status} -> {to_status} is guarded")
