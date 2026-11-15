# Jev layer (P5)

Wraps Jev (TypeSafe) so nobody else in the codebase calls it directly —
everything goes through [`decide()`](decide.py). See the "Where Jev fits"
and "Jev wrapper" sections of [jev-uw-team-plan.md](../../../../jev-uw-team-plan.md)
for the design this follows.

## What's here

- `questions.py` — the fixed library of the seven Jev questions (`route`,
  `ready`, `page_state`, `next_action`, `rank_fit`, `is_commit`, `success`).
- `thresholds.py` — per-question confidence thresholds and what to do below
  them. All placeholders at 0.8 per the plan; real numbers come from
  `evals/` once there's a labeled set per question and (eventually) a real
  Jev key to test against.
- `client.py` — low-level HTTP client: retries with backoff on timeouts/5xx/429,
  no retry on other 4xx. **The request/response field names are UNCONFIRMED**
  — copied from the example in the team plan, not from real TypeSafe docs,
  because we don't have an API key yet. Check `_parse_jev_response` in
  `decide.py` against the real response shape as soon as one exists.
- `fallback.py` — `HeuristicFallback` (offline, keyword-based, used in tests
  and as the harness baseline) and `AnthropicFallback` (calls Claude, needs
  `ANTHROPIC_API_KEY`) for when Jev is down or rate-limited.
- `decide.py` — the entrypoint. Tries Jev, falls back to the LLM classifier
  per question on `JevUnavailableError`, logs every call via `logging_util.py`.
- `logging_util.py` — structured per-call latency/cost logging.

## Status / what's blocked

- **No real Jev API key yet** (early access) — `JevClient` always raises
  `JevUnavailableError` and every call runs through the fallback until one
  is set via `JEV_API_KEY` / `JEV_API_BASE_URL`.
- **Not wired into a FastAPI app yet** — that's P2's `/decide` route and
  schemas (`shared/schemas/`), which don't exist in this repo yet. This
  package has no dependency on them; it's a plain Python module ready to be
  imported once that scaffolding lands.
- **`page_state` / `next_action` have no real site fixtures yet** — those
  come from P6 (Charlie)'s adapters. `evals/datasets/page_state_v1.jsonl` is
  synthetic in the meantime.

## Running tests

```
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
```
