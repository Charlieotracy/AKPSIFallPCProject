"""Request flow step 2: turn a routed message into a module's parameters.

Jev `route` has already picked the module. One Claude call fills that module's
schema (structured output, so the reply is always schema-shaped JSON). The caller
then checks `result.missing`: if it's non-empty the task goes to `needs_info`
without spending a Jev call; otherwise Jev `ready` makes the final call.

Logging never includes the user's message (it may hold health details).
"""

from __future__ import annotations

import logging
from datetime import datetime
from functools import cache
from pathlib import Path

import anthropic
import pydantic
from pydantic import BaseModel

from .schemas import CENTRAL, EXTRACTION_MODELS, Kind, Module, ModuleParams

log = logging.getLogger(__name__)

PROMPT_VERSION = "extract_v1"
DEFAULT_MODEL = "claude-opus-5-5"
_PROMPT_DIR = Path(__file__).parent / "prompts"


class ExtractionError(Exception):
    """Claude declined or returned nothing usable. Caller should ask the user to rephrase."""


class ExtractionResult(BaseModel):
    module: Module
    kind: Kind
    params: ModuleParams
    missing: list[str]  # non-empty -> needs_info, skip Jev `ready`
    prompt_version: str
    model: str  # the model that answered; differs from the requested one if a fallback ran


@cache
def load_prompt(version: str = PROMPT_VERSION) -> str:
    return (_PROMPT_DIR / f"{version}.md").read_text(encoding="utf-8")


def build_system_prompt(module: Module, version: str = PROMPT_VERSION) -> str:
    return load_prompt(version).replace("{module}", module)


def build_user_turn(message: str, now: datetime) -> str:
    local = now.astimezone(CENTRAL)
    # Weekday name included so "Thursday" resolves without date arithmetic.
    stamp = local.strftime("%A %Y-%m-%d %H:%M %Z")
    return f"Current time: {stamp}\n\n<message>\n{message}\n</message>"


async def extract(
    module: Module,
    message: str,
    *,
    client: anthropic.AsyncAnthropic,
    now: datetime | None = None,
    model: str = DEFAULT_MODEL,
) -> ExtractionResult:
    now = now or datetime.now(CENTRAL)
    output_model = EXTRACTION_MODELS[module]

    try:
        response = await client.beta.messages.parse(
            model=model,
            max_tokens=16000,
            system=build_system_prompt(module),
            messages=[{"role": "user", "content": build_user_turn(message, now)}],
            output_format=output_model,
            # Short, latency-sensitive extraction: low effort is enough.
            output_config={"effort": "low"},
            # If a safety classifier misfires (possible on UHS health wording), the API
            # retries on a fallback model inside the same call instead of failing.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except pydantic.ValidationError as e:
        # Schema-shaped but breaks a constraint the API can't enforce (e.g. quantity > 8).
        raise ExtractionError(f"output failed validation: {e.error_count()} error(s)") from e

    if response.stop_reason == "refusal":
        raise ExtractionError("model declined the request")
    parsed = response.parsed_output
    if parsed is None:
        raise ExtractionError(f"no parsed output (stop_reason={response.stop_reason})")

    result = ExtractionResult(
        module=module,
        kind=parsed.kind,
        params=parsed.params,
        missing=parsed.params.missing_fields(),
        prompt_version=PROMPT_VERSION,
        model=response.model,
    )
    log.info(
        "extract module=%s kind=%s missing=%s model=%s request_id=%s",
        module,
        result.kind,
        result.missing,
        result.model,
        getattr(response, "_request_id", None),
    )
    return result
