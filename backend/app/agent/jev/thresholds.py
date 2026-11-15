"""Confidence thresholds per question.

Placeholder values per the team plan: start at ~0.8 for everything, replace
with real numbers once the eval harness (evals/) has run against labeled
data in week 5. `is_commit` is intentionally biased toward "ask anyway" —
a low threshold with below_threshold="assume_true" so a miss never slips
through uncaught; extra confirmations are an acceptable cost.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

BelowThresholdAction = Literal["ask_user", "llm_fallback", "stop", "assume_true"]


class ThresholdConfig(BaseModel):
    min_confidence: float
    below_threshold: BelowThresholdAction


DEFAULT_THRESHOLDS: dict[str, ThresholdConfig] = {
    "route": ThresholdConfig(min_confidence=0.8, below_threshold="ask_user"),
    "ready": ThresholdConfig(min_confidence=0.8, below_threshold="ask_user"),
    "page_state": ThresholdConfig(min_confidence=0.8, below_threshold="stop"),
    "next_action": ThresholdConfig(min_confidence=0.8, below_threshold="stop"),
    "rank_fit": ThresholdConfig(min_confidence=0.0, below_threshold="ask_user"),  # score, not gated
    "is_commit": ThresholdConfig(min_confidence=0.8, below_threshold="assume_true"),
    "success": ThresholdConfig(min_confidence=0.8, below_threshold="ask_user"),
}


def load_thresholds(path: str | None = None) -> dict[str, ThresholdConfig]:
    """Load thresholds from a YAML file (same shape as DEFAULT_THRESHOLDS),
    falling back to the defaults above when no file is given or found."""
    if path is None:
        return DEFAULT_THRESHOLDS

    import yaml

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    merged = dict(DEFAULT_THRESHOLDS)
    for name, cfg in raw.items():
        merged[name] = ThresholdConfig(**cfg)
    return merged


def passes_threshold(question: str, confidence: float, thresholds: dict[str, ThresholdConfig] | None = None) -> bool:
    cfg = (thresholds or DEFAULT_THRESHOLDS)[question]
    return confidence >= cfg.min_confidence
