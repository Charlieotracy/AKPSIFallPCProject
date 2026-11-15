"""The fixed library of Jev questions used across the assistant.

One entry per row of the "Where Jev fits" table in jev-uw-team-plan.md.
Adapters and the orchestrator should pull questions from here by name
rather than constructing ad-hoc Question objects, so instructions/options
stay consistent and versioned in one place.
"""

from __future__ import annotations

from .models import Question

QUESTIONS: dict[str, Question] = {
    "route": Question(
        type="choice",
        instructions="Which module should handle this message?",
        options=["courses", "uhs", "cbtf", "tickets", "other"],
    ),
    "ready": Question(
        type="noul",
        instructions=(
            "True if enough parameters are known to search now; false if a "
            "follow-up question is needed first."
        ),
    ),
    "page_state": Question(
        type="choice",
        instructions="Which state is this page in?",
        options=["login_required", "expected_page", "error", "unexpected"],
    ),
    "next_action": Question(
        type="choice",
        # options are the indexed interactive elements on the page snapshot;
        # callers must fill `options` in per call (element indices as strings,
        # plus "stop") since the set changes every page.
        instructions=(
            "Which indexed element should be acted on next to make progress "
            "toward the task, or 'stop' if none is safe/correct?"
        ),
        options=None,
    ),
    "rank_fit": Question(
        type="score",
        instructions=(
            "Score how well this candidate fits the user's schedule and "
            "stated preferences, from 0 (bad fit) to 1 (ideal)."
        ),
    ),
    "is_commit": Question(
        type="noul",
        instructions=(
            "True if clicking/submitting this element creates, changes, "
            "cancels, or pays for something (i.e. requires a confirm token "
            "before it is allowed). False positives are fine; misses are not."
        ),
    ),
    "success": Question(
        type="noul",
        instructions="True if the result page shows the committed action succeeded.",
    ),
}


def get_question(name: str, **overrides) -> Question:
    """Look up a library question, optionally overriding fields (e.g. a
    fresh `options` list for next_action, built from the current snapshot)."""
    base = QUESTIONS[name]
    return base.model_copy(update=overrides)
