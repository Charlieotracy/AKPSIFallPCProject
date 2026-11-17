"""Per-module parameter schemas the orchestrator fills from a user's message.

Where this sits in the request flow (team plan, "Request flow"):

    Jev `route` picks the module
      -> extract() fills that module's params          (this package)
      -> missing_fields() non-empty? ask a follow-up   (no Jev call needed)
      -> otherwise Jev `ready` decides search vs. ask

Every field a user might leave out is optional, so extraction never fails just
because a message is incomplete. `missing_fields()` reports what still has to be
asked before a search can run. The Field descriptions are sent to Claude as part
of the output schema, so they double as extraction instructions.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

CENTRAL = ZoneInfo("America/Chicago")

Module = Literal["courses", "uhs", "cbtf", "tickets"]
Kind = Literal["search", "book", "watch"]
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _assume_central(value: datetime) -> datetime:
    """Treat a datetime without an offset as Madison local time."""
    return value.replace(tzinfo=CENTRAL) if value.tzinfo is None else value


LocalDateTime = Annotated[datetime, AfterValidator(_assume_central)]


class _Params(BaseModel):
    # forbid: Claude can't add fields we didn't define (matters most for UHS, see below).
    model_config = ConfigDict(extra="forbid")

    def missing_fields(self) -> list[str]:
        """What must be asked before searching. Names are topics for the follow-up question."""
        return []


class CoursesParams(_Params):
    course: str | None = Field(
        None,
        description='Subject and catalog number, subject uppercased, e.g. "CS 354", "MATH 222". '
        "Null unless the user names a specific course.",
    )
    keywords: str | None = Field(
        None,
        description='Topic words for open-ended searches, e.g. "intro psych". Null if a course is named.',
    )
    term: str | None = Field(
        None, description='Season and year, e.g. "Spring 2027". Null if not said.'
    )
    section: str | None = Field(None, description='Section if named, e.g. "LEC 002", "DIS 301".')
    days: list[Weekday] = Field(default_factory=list, description="Days the class should meet on.")
    earliest_time: time | None = Field(
        None, description="Class should start at or after this time."
    )
    latest_time: time | None = Field(None, description="Class should end by this time.")

    def missing_fields(self) -> list[str]:
        return [] if (self.course or self.keywords) else ["course"]


# Placeholder list until P6 records MyUHS fixtures and we see the real appointment types.
# Anything that maps to "other" will usually end in `handed_off` (call 608-265-5600).
UhsCategory = Literal["primary_care", "mental_health", "immunization", "sexual_health", "other"]


class UhsParams(_Params):
    """Deliberately has no free-text field.

    Plan rule: the visit reason goes to the LLM only to pick a category. With no text
    field and extra="forbid", health details can't end up in Task.params or the DB.
    """

    category: UhsCategory | None = Field(
        None,
        description="Appointment category implied by the visit reason. Null if no reason is given.",
    )
    earliest: LocalDateTime | None = Field(None, description="Earliest acceptable start time.")
    latest: LocalDateTime | None = Field(None, description="Latest acceptable start time.")

    def missing_fields(self) -> list[str]:
        return [] if self.category else ["category"]


class CbtfParams(_Params):
    # The plan's draft has `course: str`. Optional here so "book my midterm" still
    # extracts, and then missing_fields() triggers "Which course?".
    course: str | None = Field(
        None, description='Subject and catalog number, subject uppercased, e.g. "CS 354".'
    )
    exam: str | None = Field(
        None, description='Exam name as the user says it, e.g. "Midterm", "Exam 2", "Quiz".'
    )
    earliest: LocalDateTime | None = Field(None, description="Earliest acceptable start time.")
    latest: LocalDateTime | None = Field(None, description="Latest acceptable start time.")

    def missing_fields(self) -> list[str]:
        return [] if self.course else ["course"]


Sport = Literal["football", "mens_basketball", "womens_basketball"]


class TicketsParams(_Params):
    sport: Sport | None = Field(
        None,
        description="Null if the sport is unclear (e.g. \"basketball\" without men's/women's).",
    )
    opponent: str | None = Field(None, description='Opposing team, e.g. "Ohio State".')
    game_date: date | None = Field(None, description="Date of the game, if given.")
    quantity: int = Field(1, ge=1, le=8, description="Number of tickets.")
    max_price: float | None = Field(None, ge=0, description="Max price per ticket in USD.")

    def missing_fields(self) -> list[str]:
        missing = [] if self.sport else ["sport"]
        if not (self.opponent or self.game_date):
            missing.append("game")
        return missing


ModuleParams = CoursesParams | UhsParams | CbtfParams | TicketsParams


# What Claude returns: a task kind plus that module's params. The kind enum is per
# module, so the schema itself rules out invalid combinations.
class CoursesExtraction(BaseModel):
    kind: Literal["search", "watch", "book"]
    params: CoursesParams


class UhsExtraction(BaseModel):
    kind: Literal["search", "watch", "book"]
    params: UhsParams


class CbtfExtraction(BaseModel):
    kind: Literal["search", "watch", "book"]
    params: CbtfParams


class TicketsExtraction(BaseModel):
    # No "book": hard rule, we never buy tickets. A purchase request becomes a search.
    kind: Literal["search", "watch"]
    params: TicketsParams


EXTRACTION_MODELS: dict[Module, type[BaseModel]] = {
    "courses": CoursesExtraction,
    "uhs": UhsExtraction,
    "cbtf": CbtfExtraction,
    "tickets": TicketsExtraction,
}
