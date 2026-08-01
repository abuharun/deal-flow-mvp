"""Request/response contracts for founder AI-analysis job endpoints.

Response fields are deliberately a SUBSET of the analysis_jobs row: token
counts, cost estimate, model, and prompt_version never cross this boundary
-- those are internal worker/billing bookkeeping, not founder-facing status.
last_error_code/message_key are safe, bounded, fixed-charset values (never
free text), so a failure can never leak provider or exception detail.

AnalysisCompletionInput/AnalysisFailureInput are the schema-level guard the
future worker's state machine validates against BEFORE touching the row;
the same bounds are enforced again by the model's DB CHECKs as a backstop.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.analysis_job import (
    MAX_COST_ESTIMATE_USD,
    MAX_ERROR_CODE_LENGTH,
    MAX_ERROR_MESSAGE_KEY_LENGTH,
    MAX_MODEL_LENGTH,
    MAX_PROMPT_VERSION_LENGTH,
)

ERROR_CODE_PATTERN = rf"^[A-Z0-9_]{{1,{MAX_ERROR_CODE_LENGTH}}}$"
ERROR_MESSAGE_KEY_PATTERN = r"^[a-z][a-zA-Z0-9]*(\.[a-z][a-zA-Z0-9]*)+$"


class AnalysisTriggerRequest(BaseModel):
    """No body, or an exact empty object -- nothing else is accepted."""

    model_config = ConfigDict(extra="forbid")


class AnalysisJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    startup_id: uuid.UUID
    input_revision: int
    status: str
    attempts: int
    max_attempts: int
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    next_attempt_at: datetime | None
    last_error_code: str | None
    last_error_message_key: str | None
    stale: bool
    created_at: datetime
    updated_at: datetime


class AnalysisCompletionInput(BaseModel):
    """Validated success write for the future worker; never populated by calling a real provider."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, min_length=1, max_length=MAX_MODEL_LENGTH)
    prompt_version: str | None = Field(
        default=None, min_length=1, max_length=MAX_PROMPT_VERSION_LENGTH
    )
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_estimate_usd: Decimal | None = Field(default=None, ge=0, le=MAX_COST_ESTIMATE_USD)


class AnalysisFailureInput(BaseModel):
    """Validated failure write: safe, bounded, fixed-charset fields only -- never free text."""

    model_config = ConfigDict(extra="forbid")

    error_code: str = Field(pattern=ERROR_CODE_PATTERN)
    error_message_key: str = Field(
        pattern=ERROR_MESSAGE_KEY_PATTERN, max_length=MAX_ERROR_MESSAGE_KEY_LENGTH
    )
