"""Orchestrator extraction tests.

Offline tests use a fake client and run in CI. The live test sends the 20 samples in
fixtures/extraction_samples.jsonl to Claude and is opt-in (costs money):

    JEV_LIVE_TESTS=1 pytest -m live -s
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args

import anthropic
import pydantic
import pytest

from app.agent.orchestrator import EXTRACTION_MODELS, ExtractionError, extract
from app.agent.orchestrator.extract import build_system_prompt, build_user_turn
from app.agent.orchestrator.schemas import (
    CENTRAL,
    CbtfExtraction,
    CbtfParams,
    Module,
    TicketsExtraction,
    TicketsParams,
    UhsParams,
)

SAMPLES_PATH = Path(__file__).parent / "fixtures" / "extraction_samples.jsonl"
SAMPLES = [json.loads(line) for line in SAMPLES_PATH.read_text().splitlines() if line.strip()]
# Every sample's relative dates ("Thursday", "tomorrow") are written against this moment.
SAMPLE_NOW = datetime(2026, 11, 16, 10, 0, tzinfo=CENTRAL)  # Monday


class FakeClient:
    """Stands in for AsyncAnthropic: records the parse() call and returns a canned reply."""

    def __init__(
        self, parsed: Any = None, stop_reason: str = "end_turn", error: Exception | None = None
    ):
        self.calls: list[dict[str, Any]] = []

        async def parse(**kwargs: Any) -> SimpleNamespace:
            self.calls.append(kwargs)
            if error:
                raise error
            return SimpleNamespace(
                stop_reason=stop_reason,
                parsed_output=parsed,
                model=kwargs["model"],
                _request_id="req_test",
            )

        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=parse))


# --- fixtures and schemas -------------------------------------------------------------


def test_samples_cover_every_module_and_match_schemas():
    assert len(SAMPLES) == 20
    assert len({s["id"] for s in SAMPLES}) == 20
    for module in get_args(Module):
        assert sum(s["module"] == module for s in SAMPLES) == 5, module
    for s in SAMPLES:
        # Catches typos in labels (e.g. "mental-health", or kind "book" for tickets).
        exp = s["expected"]
        EXTRACTION_MODELS[s["module"]].model_validate(
            {"kind": exp["kind"], "params": exp["params"]}
        )


@pytest.mark.parametrize("module", get_args(Module))
def test_output_schema_accepted_by_sdk(module):
    anthropic.transform_schema(EXTRACTION_MODELS[module].model_json_schema())


def test_tickets_can_never_be_booked():
    with pytest.raises(pydantic.ValidationError):
        TicketsExtraction.model_validate({"kind": "book", "params": {}})


def test_uhs_params_reject_free_text():
    # No field can carry the visit reason into Task.params.
    with pytest.raises(pydantic.ValidationError):
        UhsParams.model_validate({"category": "other", "reason": "rash on my arm"})


def test_naive_datetime_is_read_as_madison_time():
    p = CbtfParams(course="CS 354", earliest="2026-11-19T14:00:00")
    assert p.earliest.utcoffset() == timedelta(hours=-6)  # CST in November


@pytest.mark.parametrize(
    ("params", "missing"),
    [
        (CbtfParams(), ["course"]),
        (CbtfParams(course="CS 354"), []),
        (UhsParams(), ["category"]),
        (TicketsParams(), ["sport", "game"]),
        (TicketsParams(sport="football", opponent="Iowa"), []),
    ],
)
def test_missing_fields(params, missing):
    assert params.missing_fields() == missing


# --- prompt -------------------------------------------------------------------------


@pytest.mark.parametrize("module", get_args(Module))
def test_system_prompt_renders(module):
    prompt = build_system_prompt(module)
    assert "{module}" not in prompt
    assert f"**{module}**" in prompt


def test_user_turn_has_weekday_and_wraps_message():
    turn = build_user_turn("book my midterm", SAMPLE_NOW)
    assert "Monday 2026-11-16 10:00" in turn
    assert "<message>\nbook my midterm\n</message>" in turn


# --- extract() with a fake client --------------------------------------------------------


async def test_extract_returns_result_and_sends_expected_request():
    parsed = CbtfExtraction(kind="book", params=CbtfParams(course="CS 354", exam="Midterm"))
    client = FakeClient(parsed)

    result = await extract("cbtf", "Book my CS 354 midterm", client=client, now=SAMPLE_NOW)

    assert (result.module, result.kind, result.missing) == ("cbtf", "book", [])
    assert result.params.course == "CS 354"
    assert result.prompt_version == "extract_v1"
    (call,) = client.calls
    assert call["output_format"] is CbtfExtraction
    assert call["fallbacks"] == "default"
    assert call["output_config"] == {"effort": "low"}
    assert "**cbtf**" in call["system"]


async def test_extract_reports_missing_fields():
    client = FakeClient(CbtfExtraction(kind="book", params=CbtfParams(exam="Midterm")))
    result = await extract("cbtf", "reserve a slot for my midterm", client=client, now=SAMPLE_NOW)
    assert result.missing == ["course"]


async def test_refusal_raises():
    client = FakeClient(parsed=None, stop_reason="refusal")
    with pytest.raises(ExtractionError, match="declined"):
        await extract("uhs", "anything", client=client, now=SAMPLE_NOW)


async def test_invalid_output_raises_extraction_error():
    try:
        TicketsParams(quantity=50)
    except pydantic.ValidationError as e:
        error = e
    client = FakeClient(error=error)
    with pytest.raises(ExtractionError, match="validation"):
        await extract("tickets", "50 tickets please", client=client, now=SAMPLE_NOW)


# --- live: the 20 samples against Claude ------------------------------------------------


def _norm(value: Any) -> Any:
    """Make expected and actual comparable: case-insensitive text, datetimes to the minute."""
    if isinstance(value, str):
        if "T" in value and value[:4].isdigit():
            return datetime.fromisoformat(value).replace(second=0, microsecond=0)
        return value.strip().casefold()
    if isinstance(value, list):
        return sorted(_norm(v) for v in value)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return value


def _diff(expected: dict[str, Any], result: Any) -> list[str]:
    actual = result.params.model_dump(mode="json")
    problems = []
    if result.kind != expected["kind"]:
        problems.append(f"kind: expected {expected['kind']!r}, got {result.kind!r}")
    for key, want in expected["params"].items():
        if _norm(actual[key]) != _norm(want):
            problems.append(f"{key}: expected {want!r}, got {actual[key]!r}")
    if result.missing != expected["missing"]:
        problems.append(f"missing: expected {expected['missing']}, got {result.missing}")
    return problems


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("JEV_LIVE_TESTS") != "1", reason="set JEV_LIVE_TESTS=1 to call Claude"
)
async def test_live_extraction_on_samples():
    client = anthropic.AsyncAnthropic()
    limit = asyncio.Semaphore(5)

    async def run(sample: dict[str, Any]) -> tuple[str, list[str]]:
        async with limit:
            try:
                result = await extract(
                    sample["module"], sample["message"], client=client, now=SAMPLE_NOW
                )
            except ExtractionError as e:
                return sample["id"], [f"error: {e}"]
            return sample["id"], _diff(sample["expected"], result)

    outcomes = await asyncio.gather(*(run(s) for s in SAMPLES))
    failures = [(sid, probs) for sid, probs in outcomes if probs]
    print(f"\nextraction: {len(SAMPLES) - len(failures)}/{len(SAMPLES)} samples correct")
    for sid, probs in failures:
        print(f"  {sid}: " + "; ".join(probs))
    assert not failures
