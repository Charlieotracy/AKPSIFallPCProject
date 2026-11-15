# Evals (P5)

Labeled datasets and a harness for the four decisions in P5's scope, per
[jev-uw-team-plan.md](../jev-uw-team-plan.md): "P5's four labeled sets:
routing messages, readiness cases, page states (from fixtures), commit vs
non-commit actions."

## Datasets

| File | Question | n | Notes |
|---|---|---|---|
| `datasets/routing_v1.jsonl` | `route` | 36 | Hand-written sample messages across all five routes (`courses`/`uhs`/`cbtf`/`tickets`/`other`), including a few deliberately ambiguous ones (e.g. "parking tickets" → `other`, not `tickets`). |
| `datasets/readiness_v1.jsonl` | `ready` | 20 | Synthetic param dicts per module; some have a missing optional field but are still `ready: true` on purpose — readiness is a judgment call, not just "no nulls". |
| `datasets/page_state_v1.jsonl` | `page_state` | 15 | **Synthetic, not from real fixtures.** P6 (Charlie) hasn't recorded site fixtures yet; replace this file once `fixtures/` exists. |
| `datasets/commit_v1.jsonl` | `is_commit` | 18 | Synthetic click-target descriptions. Biased toward labeling ambiguous actions `true` to match the "false positives are fine; misses are not" rule. |

## Running the harness

```
python3 evals/harness.py            # all four datasets
python3 evals/harness.py routing    # just one
```

It currently scores `HeuristicFallback` (see `backend/app/agent/jev/fallback.py`)
since there's no Jev API key yet — this is a **baseline for the fallback
path**, not Jev's accuracy. The same harness will score real Jev decisions
unchanged once `decide()` has a key to call; swap `HeuristicFallback()` in
`harness.py` for a real `JevClient` call at that point.

Current baseline (fallback classifier only):

| Dataset | Accuracy |
|---|---|
| routing | ~86% |
| readiness | ~60% |
| page_state | ~47% |
| commit | ~56% |

These numbers are expected to be mediocre — the heuristic fallback exists
as a safety net, not a real classifier. They're a starting point for
threshold tuning in week 5, and a regression check: if a change to
`fallback.py` makes these numbers drop, something broke.

## Threshold tuning (week 5)

Once real Jev responses are available, re-run the harness against Jev
instead of the fallback, check calibration (does high confidence actually
mean correct?) per question, and update `backend/app/agent/jev/thresholds.py`
accordingly. `is_commit` is the one exception: tune its threshold so it
never misses a true commit on this dataset, even if that means more false
positives (extra user confirmations) than a naively "optimal" threshold
would give.
