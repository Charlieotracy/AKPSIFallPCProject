"""Eval harness for the four P5 labeled sets (routing, readiness, page
state, commit vs non-commit).

Jev isn't reachable yet (no API key, see jev-uw-team-plan.md), so this runs
each case through the HeuristicFallback classifier directly. That gives a
real accuracy/calibration baseline today and the exact same code path will
exercise Jev once a key exists — only the `source` field in each Decision
changes. Threshold tuning can start now on the fallback and get re-run once
Jev is in the loop.

Usage:
    python evals/harness.py                 # run all four datasets
    python evals/harness.py routing         # run one dataset
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.agent.jev.fallback import HeuristicFallback  # noqa: E402
from app.agent.jev.questions import QUESTIONS  # noqa: E402

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"

DATASET_SPECS = {
    "routing": {
        "file": "routing_v1.jsonl",
        "question": "route",
        "state_key": "text",
    },
    "readiness": {
        "file": "readiness_v1.jsonl",
        "question": "ready",
        "state_key": "state",
    },
    "page_state": {
        "file": "page_state_v1.jsonl",
        "question": "page_state",
        "state_key": "state",
    },
    "commit": {
        "file": "commit_v1.jsonl",
        "question": "is_commit",
        "state_key": "state",
    },
}


def load_dataset(name: str) -> list[dict]:
    spec = DATASET_SPECS[name]
    path = DATASETS_DIR / spec["file"]
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def run_dataset(name: str, fallback: HeuristicFallback) -> dict:
    spec = DATASET_SPECS[name]
    question = QUESTIONS[spec["question"]]
    cases = load_dataset(name)

    correct = 0
    # Calibration: for each case, bucket by confidence and track whether
    # the answer was right, so we can see if "high confidence" tracks
    # "actually correct" once real thresholds get picked.
    buckets: dict[str, list[bool]] = {"0.0-0.3": [], "0.3-0.6": [], "0.6-1.0": []}

    for case in cases:
        state = case[spec["state_key"]]
        decision = fallback.classify(spec["question"], question, state)
        is_correct = decision.answer == case["label"]
        correct += int(is_correct)

        if decision.confidence < 0.3:
            buckets["0.0-0.3"].append(is_correct)
        elif decision.confidence < 0.6:
            buckets["0.3-0.6"].append(is_correct)
        else:
            buckets["0.6-1.0"].append(is_correct)

    accuracy = correct / len(cases)
    calibration = {
        bucket: (sum(results) / len(results) if results else None, len(results))
        for bucket, results in buckets.items()
    }
    return {"n": len(cases), "accuracy": accuracy, "calibration": calibration}


def main(names: list[str]) -> None:
    fallback = HeuristicFallback()
    for name in names:
        report = run_dataset(name, fallback)
        print(f"\n=== {name} (n={report['n']}) ===")
        print(f"accuracy: {report['accuracy']:.2%}")
        print("calibration (confidence bucket -> accuracy, n):")
        for bucket, (acc, n) in report["calibration"].items():
            acc_str = f"{acc:.2%}" if acc is not None else "n/a"
            print(f"  {bucket}: {acc_str} (n={n})")


if __name__ == "__main__":
    names = sys.argv[1:] or list(DATASET_SPECS)
    main(names)
