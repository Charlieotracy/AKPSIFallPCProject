"""Pure tests of the transition table (INV-2, INV-3, INV-9). No database."""

from __future__ import annotations

import itertools

import pytest

from app.domain.errors import GuardedTransition, IllegalTransition
from app.domain.tasks import (
    TERMINAL_STATUSES,
    TRANSITIONS,
    Kind,
    TaskStatus,
    check_transition,
)

S = TaskStatus
K = Kind
EDGE_PAIRS = {(e.from_status, e.to_status) for e in TRANSITIONS}
NON_TERMINAL = [s for s in TaskStatus if s not in TERMINAL_STATUSES]


def _allowed_kinds(edge):
    return edge.kinds if edge.kinds is not None else frozenset(Kind)


@pytest.mark.parametrize("edge", [e for e in TRANSITIONS if not e.guarded], ids=str)
def test_every_unguarded_edge_passes_for_each_allowed_kind(edge):
    for kind in _allowed_kinds(edge):
        check_transition(kind, edge.from_status, edge.to_status)


@pytest.mark.parametrize("edge", [e for e in TRANSITIONS if e.kinds is not None], ids=str)
def test_kind_restricted_edges_reject_other_kinds(edge):
    for kind in set(Kind) - edge.kinds:
        with pytest.raises(IllegalTransition):
            check_transition(kind, edge.from_status, edge.to_status)


def test_every_pair_outside_the_table_is_rejected_for_all_kinds():
    for from_status, to_status in itertools.product(TaskStatus, TaskStatus):
        if (from_status, to_status) in EDGE_PAIRS:
            continue
        for kind in Kind:
            with pytest.raises(IllegalTransition):
                check_transition(kind, from_status, to_status)


def test_executing_is_guarded_even_for_book_tasks():
    with pytest.raises(GuardedTransition):
        check_transition(K.BOOK, S.AWAITING_CONFIRM, S.EXECUTING)


def test_guarded_edge_is_the_only_way_into_executing():
    into_executing = [e for e in TRANSITIONS if e.to_status is S.EXECUTING]
    assert len(into_executing) == 1 and into_executing[0].guarded


def test_terminal_statuses_have_no_outgoing_edges():
    assert not [e for e in TRANSITIONS if e.from_status in TERMINAL_STATUSES]


@pytest.mark.parametrize("status", NON_TERMINAL, ids=str)
def test_every_non_terminal_status_can_fail_and_hand_off(status):
    assert (status, S.FAILED) in EDGE_PAIRS
    assert (status, S.HANDED_OFF) in EDGE_PAIRS


@pytest.mark.parametrize("status", NON_TERMINAL, ids=str)
def test_cancel_allowed_everywhere_except_executing(status):
    assert ((status, S.CANCELLED) in EDGE_PAIRS) is (status is not S.EXECUTING)


def test_no_edge_from_awaiting_login_into_booking_statuses():
    for target in (S.AWAITING_CONFIRM, S.CANDIDATES, S.EXECUTING):
        assert (S.AWAITING_LOGIN, target) not in EDGE_PAIRS


def test_failed_is_terminal_so_no_retry_edges():
    assert (S.FAILED, S.READY) not in EDGE_PAIRS
    assert (S.FAILED, S.CANDIDATES) not in EDGE_PAIRS


# Kind spot-checks from the transition table (the first is named in CUJ 3).
@pytest.mark.parametrize(
    ("kind", "from_status", "to_status"),
    [
        (K.SEARCH, S.SEARCHING, S.CANDIDATES),
        (K.BOOK, S.READY, S.WATCHING),
        (K.WATCH, S.READY, S.SEARCHING),
        (K.SEARCH, S.CANDIDATES, S.AWAITING_CONFIRM),
    ],
)
def test_kind_spot_checks_rejected(kind, from_status, to_status):
    with pytest.raises(IllegalTransition):
        check_transition(kind, from_status, to_status)
