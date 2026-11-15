"""The single entrypoint everyone else calls instead of touching Jev or the
fallback classifier directly, so retries, logging, and fallback behavior
live in one place (per jev-uw-team-plan.md: "Nobody calls Jev directly").
"""

from __future__ import annotations

from .client import JevClient, JevUnavailableError
from .fallback import FallbackClassifier, HeuristicFallback
from .logging_util import timed_call
from .models import Decision, Question


def decide(
    state: str | dict,
    questions: dict[str, Question],
    client: JevClient | None = None,
    fallback: FallbackClassifier | None = None,
) -> dict[str, Decision]:
    """Answer each named question against `state`.

    Tries Jev first for the whole batch; if Jev is unavailable, falls back
    to an LLM classifier per question so a single outage doesn't block every
    decision type.
    """
    client = client or JevClient()
    fallback = fallback or HeuristicFallback()

    try:
        with timed_call("+".join(questions), "jev") as finish:
            raw = client.decide_raw(state, questions)
            decisions = _parse_jev_response(raw, questions)
            avg_conf = sum(d.confidence for d in decisions.values()) / len(decisions)
            finish(confidence=avg_conf, cost_usd=raw.get("usage", {}).get("cost_usd"))
        return decisions
    except JevUnavailableError:
        return {
            name: _classify_with_logging(fallback, name, q, state)
            for name, q in questions.items()
        }


def _classify_with_logging(fallback: FallbackClassifier, name: str, question: Question, state) -> Decision:
    with timed_call(name, "llm_fallback") as finish:
        decision = fallback.classify(name, question, state)
        finish(confidence=decision.confidence, cost_usd=None)
    return decision


def _parse_jev_response(raw: dict, questions: dict[str, Question]) -> dict[str, Decision]:
    """Field names here are UNCONFIRMED — adjust once we have real Jev
    responses. Assumed shape: {"answers": {name: {"answer":..., "confidence":..., ...}}}.
    """
    answers = raw.get("answers", raw)  # tolerate a flat top-level shape too
    decisions: dict[str, Decision] = {}
    for name, question in questions.items():
        entry = answers[name]
        decisions[name] = Decision(
            question=name,
            kind=question.type,
            answer=entry["answer"],
            confidence=float(entry.get("confidence", 0.0)),
            source="jev",
            raw=entry,
        )
    return decisions
