import os

from app.agent.jev import JevClient, Question, decide
from app.agent.jev.models import Decision
from app.agent.jev.questions import QUESTIONS, get_question
from app.agent.jev.thresholds import DEFAULT_THRESHOLDS, passes_threshold


def test_decide_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    client = JevClient()  # no key -> JevUnavailableError inside decide()

    result = decide("Help me book my CS 354 midterm at the CBTF", {"route": QUESTIONS["route"]}, client=client)

    assert "route" in result
    decision = result["route"]
    assert isinstance(decision, Decision)
    assert decision.source == "llm_fallback"
    assert decision.answer == "cbtf"


def test_decide_normalizes_a_successful_jev_response(monkeypatch):
    client = JevClient(api_key="fake")

    def fake_decide_raw(state, questions):
        return {"answers": {"route": {"answer": "courses", "confidence": 0.93}}}

    monkeypatch.setattr(client, "decide_raw", fake_decide_raw)

    result = decide("is CS 354 open", {"route": QUESTIONS["route"]}, client=client)

    decision = result["route"]
    assert decision.source == "jev"
    assert decision.answer == "courses"
    assert decision.confidence == 0.93


def test_is_commit_never_lands_below_assume_true_safety_net():
    """is_commit must never silently resolve to 'not a commit' when the
    fallback is unsure — low confidence routes to assume_true per thresholds.py,
    not to treating the action as safe."""
    from app.agent.jev.fallback import HeuristicFallback

    fallback = HeuristicFallback()
    decision = fallback.classify("is_commit", QUESTIONS["is_commit"], "click element 4")

    assert decision.answer is True
    if decision.confidence < DEFAULT_THRESHOLDS["is_commit"].min_confidence:
        assert DEFAULT_THRESHOLDS["is_commit"].below_threshold == "assume_true"


def test_get_question_override_for_next_action():
    q = get_question("next_action", options=["0", "1", "2", "stop"])
    assert q.options == ["0", "1", "2", "stop"]
    # library copy is untouched
    assert QUESTIONS["next_action"].options is None


def test_passes_threshold():
    assert passes_threshold("route", 0.95) is True
    assert passes_threshold("route", 0.1) is False
