"""Request/response contracts for founder startup + submission endpoints.

Every inbound field is length-bounded before any work happens, and the
response models are explicit projections: founder_id and any future internal
bookkeeping never leave the API by accident.
"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import StartupStatus
from app.security.urls import normalize_safe_http_url

MAX_NAME_LENGTH = 200
MAX_ONE_LINER_LENGTH = 300
MAX_SHORT_FIELD_LENGTH = 120
MAX_ANSWER_LENGTH = 10_000
MAX_FINANCIAL_TEXT_LENGTH = 500
MAX_ASK_AMOUNT = 10**15
MAX_COMPLETED_STEPS = 30

# Step identifiers are wizard bookkeeping, never free text.
_STEP_SLUG = re.compile(r"^[a-z0-9_-]{1,64}$")

_SHORT_FIELD = Field(default="", max_length=MAX_SHORT_FIELD_LENGTH)


def _stripped(value: str) -> str:
    return value.strip()


class StartupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    one_liner: str = Field(default="", max_length=MAX_ONE_LINER_LENGTH)
    sector: str = _SHORT_FIELD
    funding_stage: str = _SHORT_FIELD
    city: str = _SHORT_FIELD

    _trim = field_validator("one_liner", "sector", "funding_stage", "city")(_stripped)

    @field_validator("name")
    @classmethod
    def _name_trimmed_nonempty(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("name must not be blank")
        return trimmed


class StartupPatchRequest(BaseModel):
    """Partial metadata update: only fields the founder actually sent apply.

    Every metadata column is NOT NULL, so an explicit JSON null is a contract
    violation, not a clear — absent and null must not be conflated.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_LENGTH)
    one_liner: str | None = Field(default=None, max_length=MAX_ONE_LINER_LENGTH)
    sector: str | None = Field(default=None, max_length=MAX_SHORT_FIELD_LENGTH)
    funding_stage: str | None = Field(default=None, max_length=MAX_SHORT_FIELD_LENGTH)
    city: str | None = Field(default=None, max_length=MAX_SHORT_FIELD_LENGTH)

    @field_validator("name")
    @classmethod
    def _name_trimmed_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("name must not be blank")
        return trimmed

    @field_validator("one_liner", "sector", "funding_stage", "city")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> "StartupPatchRequest":
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError("fields may be omitted but not null")
        return self

    def changes(self) -> dict[str, str]:
        """Only the fields the request actually carried."""
        return self.model_dump(exclude_unset=True)


_ANSWER_FIELD = Field(default=None, max_length=MAX_ANSWER_LENGTH)
_FINANCIAL_TEXT_FIELD = Field(default=None, max_length=MAX_FINANCIAL_TEXT_LENGTH)


class SubmissionPatchRequest(BaseModel):
    """Autosave payload: only fields the founder actually sent apply.

    Answer columns are NOT NULL, so explicit null is rejected for them;
    the nullable financials and dataroom_url accept null as "clear".
    """

    model_config = ConfigDict(extra="forbid")

    problem: str | None = _ANSWER_FIELD
    product: str | None = _ANSWER_FIELD
    market: str | None = _ANSWER_FIELD
    traction: str | None = _ANSWER_FIELD
    team: str | None = _ANSWER_FIELD
    ask: str | None = _ANSWER_FIELD
    revenue: str | None = _FINANCIAL_TEXT_FIELD
    growth: str | None = _FINANCIAL_TEXT_FIELD
    ask_amount: int | None = Field(default=None, ge=0, le=MAX_ASK_AMOUNT)
    dataroom_url: str | None = None
    completed_steps: list[str] | None = Field(default=None, max_length=MAX_COMPLETED_STEPS)

    @field_validator("dataroom_url")
    @classmethod
    def _dataroom_url_safe_and_normalized(cls, value: str | None) -> str | None:
        # An empty string is the frontend clearing the field, same as null.
        if value is None or not value.strip():
            return None
        return normalize_safe_http_url(value)

    @field_validator("completed_steps")
    @classmethod
    def _steps_are_slugs(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for step in value:
            if not _STEP_SLUG.fullmatch(step):
                raise ValueError("completed_steps entries must be short lowercase slugs")
        # Dedupe, preserving first-seen order: autosave retries are idempotent.
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _no_explicit_nulls_for_answers(self) -> "SubmissionPatchRequest":
        for field in ("problem", "product", "market", "traction", "team", "ask"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError("answer fields may be omitted but not null")
        return self

    def changes(self) -> dict[str, object]:
        """Only the fields the request actually carried."""
        return self.model_dump(exclude_unset=True)


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    problem: str
    product: str
    market: str
    traction: str
    team: str
    ask: str
    revenue: str | None
    growth: str | None
    ask_amount: int | None
    dataroom_url: str | None
    completed_steps: list[str]
    updated_at: datetime


class StartupResponse(BaseModel):
    """Metadata projection for lists; never includes founder_id."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    one_liner: str
    sector: str
    funding_stage: str
    city: str
    status: StartupStatus
    input_revision: int
    submitted_at: datetime | None
    vc_visible_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StartupDetailResponse(StartupResponse):
    """The hydrated startup: metadata plus its one-to-one submission."""

    submission: SubmissionResponse
