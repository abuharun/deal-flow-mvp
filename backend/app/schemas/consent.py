"""Request/response contracts for founder AI/privacy consent endpoints."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.consent import MAX_TEXT_VERSION_LENGTH


class ConsentGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["ai_privacy"]
    text_version: str = Field(min_length=1, max_length=MAX_TEXT_VERSION_LENGTH)


class ConsentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    text_version: str
    granted_at: datetime


class ConsentSummaryResponse(BaseModel):
    current_version: str
    granted: bool
    history: list[ConsentResponse]
