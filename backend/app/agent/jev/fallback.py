"""LLM-classifier fallback for when Jev is down or rate-limited.

Two implementations:
- HeuristicFallback: offline, no network, no API key. Used in tests and as
  the safety net when even an LLM call would fail. Deliberately simple —
  it exists so the pipeline never hard-stops, not to be accurate.
- AnthropicFallback: calls Claude with the same (state, question) shape Jev
  would have seen, asking for a JSON {answer, confidence} object. Used in
  production when ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from .models import Decision, Question


class FallbackClassifier(Protocol):
    def classify(self, name: str, question: Question, state: str | dict) -> Decision: ...


class HeuristicFallback:
    """Keyword/structure-based guesses. No network calls."""

    _ROUTE_KEYWORDS = {
        "courses": ["course", "class", "seat", "enroll", "section", "lecture"],
        "uhs": ["uhs", "doctor", "appointment", "clinic", "sick", "vaccine", "health"],
        "cbtf": ["cbtf", "exam", "midterm", "final", "prairietest", "testing center"],
        "tickets": ["ticket", "game", "football", "basketball", "badgers"],
    }

    def classify(self, name: str, question: Question, state: str | dict) -> Decision:
        handler = getattr(self, f"_{name}", None)
        if handler is None:
            answer, confidence = self._default(question)
        else:
            answer, confidence = handler(question, state)
        return Decision(
            question=name,
            kind=question.type,
            answer=answer,
            confidence=confidence,
            source="llm_fallback",
            raw={"strategy": "heuristic"},
        )

    def _default(self, question: Question) -> tuple[str | float | bool, float]:
        if question.type == "choice":
            return (question.options or ["other"])[0], 0.0
        if question.type == "score":
            return 0.5, 0.0
        return False, 0.0

    def _route(self, question: Question, state: str | dict) -> tuple[str, float]:
        text = str(state).lower()
        for module, keywords in self._ROUTE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return module, 0.5
        return "other", 0.0

    def _is_commit(self, question: Question, state: str | dict) -> tuple[bool, float]:
        text = str(state).lower()
        commit_words = ["book", "submit", "confirm", "pay", "cancel", "enroll", "buy", "reserve"]
        # Biased toward true (false positives are fine; misses are not).
        if any(w in text for w in commit_words):
            return True, 0.6
        return True, 0.1  # low confidence -> thresholds.py routes this to "assume_true"

    def _ready(self, question: Question, state: str | dict) -> tuple[bool, float]:
        if isinstance(state, dict):
            missing = [v for v in state.values() if v is None]
            return (len(missing) == 0), 0.4
        return False, 0.0

    def _page_state(self, question: Question, state: str | dict) -> tuple[str, float]:
        text = str(state).lower()
        if "sign in" in text or "log in" in text or "netid" in text or "duo" in text:
            return "login_required", 0.5
        if "error" in text or "something went wrong" in text:
            return "error", 0.5
        return "unexpected", 0.0

    def _success(self, question: Question, state: str | dict) -> tuple[bool, float]:
        text = str(state).lower()
        if any(w in text for w in ["confirmed", "success", "reservation", "booked"]):
            return True, 0.5
        return False, 0.0


class AnthropicFallback:
    """Calls Claude as the fallback classifier. Requires ANTHROPIC_API_KEY."""

    def __init__(self, model: str = "claude-sonnet-5-5") -> None:
        self.model = model
        self._api_key = os.environ.get("ANTHROPIC_API_KEY")

    def classify(self, name: str, question: Question, state: str | dict) -> Decision:
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")

        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        options_note = f" Options: {question.options}." if question.options else ""
        prompt = (
            f"{question.instructions}{options_note}\n\n"
            f"State:\n{state}\n\n"
            'Respond with ONLY a JSON object: {"answer": <string|number|boolean>, '
            '"confidence": <0-1 float>}.'
        )
        resp = client.messages.create(
            model=self.model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        parsed = json.loads(match.group(0) if match else text)

        return Decision(
            question=name,
            kind=question.type,
            answer=parsed["answer"],
            confidence=float(parsed["confidence"]),
            source="llm_fallback",
            raw={"strategy": "anthropic", "model": self.model},
        )
