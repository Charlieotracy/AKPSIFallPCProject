"""Per-call cost/latency logging for Jev (and fallback) calls.

Kept as a tiny structured logger rather than wired into a specific metrics
backend, since we don't know yet whether P2 deploys to Render/Railway/Fly
with its own metrics story. Swap `CallLogger.emit` once that's decided.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass

logger = logging.getLogger("jev.calls")


@dataclass
class CallRecord:
    question: str
    source: str  # "jev" | "llm_fallback"
    elapsed_ms: float
    confidence: float | None
    cost_usd: float | None
    ok: bool
    error: str | None = None


class CallLogger:
    def emit(self, record: CallRecord) -> None:
        logger.info(json.dumps(asdict(record)))


_default_logger = CallLogger()


@contextmanager
def timed_call(question: str, source: str, call_logger: CallLogger = _default_logger):
    """Usage:

        with timed_call("route", "jev") as finish:
            decision = ...
            finish(confidence=decision.confidence, cost_usd=None)
    """
    start = time.perf_counter()
    result: dict = {"confidence": None, "cost_usd": None, "ok": True, "error": None}

    def finish(confidence: float | None = None, cost_usd: float | None = None) -> None:
        result["confidence"] = confidence
        result["cost_usd"] = cost_usd

    try:
        yield finish
    except Exception as exc:  # noqa: BLE001 - we want to log then re-raise
        result["ok"] = False
        result["error"] = str(exc)
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        call_logger.emit(
            CallRecord(
                question=question,
                source=source,
                elapsed_ms=elapsed_ms,
                confidence=result["confidence"],
                cost_usd=result["cost_usd"],
                ok=result["ok"],
                error=result["error"],
            )
        )
