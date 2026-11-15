from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

QuestionKind = Literal["choice", "score", "noul"]


class Question(BaseModel):
    """One named question sent to Jev, matching TypeSafe's request shape."""

    type: QuestionKind
    instructions: str
    options: list[str] | None = None  # required for "choice", unused otherwise


class Decision(BaseModel):
    """Normalized result of one question, regardless of whether Jev or the
    LLM fallback answered it."""

    question: str
    kind: QuestionKind
    answer: str | float | bool
    confidence: float
    source: Literal["jev", "llm_fallback"] = "jev"
    raw: dict = {}
