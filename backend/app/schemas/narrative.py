"""Request/response contracts for the founder-editable pitch narrative.

MVP product decision: ONE free-text narrative per startup. The founder
chooses the language they write it in, so no request or response here
carries a locale and nothing is keyed by one -- the UZ/RU UI language and
the narrative's language are independent.

Inbound text is normalized then bounded before any database work: browser
line endings collapse to \\n (rejecting a paste from a Windows editor would
be user-hostile), surrounding whitespace is trimmed so a whitespace-only
save is refused as blank, and every other control character is rejected
outright rather than silently stripped. The column's CHECK constraints
mirror these exact rules -- this layer is the friendly 422, the DB is the
guarantee.

Response projections are explicit: `NarrativeVersionSummary` (the history
list) deliberately carries no content, only its length, so listing versions
stays cheap and never ships every revision's full text.
"""

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.narrative import MAX_NARRATIVE_CONTENT_LENGTH

NarrativeSource = Literal["report_seed", "founder_edit"]

# Everything in C0 except tab and newline, plus DEL -- the same set the
# column's CHECK rejects, minus the carriage returns normalized away first.
_FORBIDDEN_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_narrative_content(value: str) -> str:
    """CRLF/CR -> LF, trimmed, with control characters refused."""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if _FORBIDDEN_CONTROL_CHARS.search(normalized):
        raise ValueError("content must not contain control characters")
    if not normalized:
        raise ValueError("content must not be blank")
    if len(normalized) > MAX_NARRATIVE_CONTENT_LENGTH:
        raise ValueError(f"content must be at most {MAX_NARRATIVE_CONTENT_LENGTH} characters")
    return normalized


class NarrativePatchRequest(BaseModel):
    """The founder's saved narrative text -- and nothing else.

    Version numbers, source, and report provenance are server-assigned; a
    client that tries to supply them gets the canonical 422 rather than a
    silently ignored field (`extra="forbid"`).
    """

    model_config = ConfigDict(extra="forbid")

    # Bounded twice on purpose: this bound rejects an absurd payload before
    # normalization runs at all, the validator re-checks the STORED length.
    content: str = Field(min_length=1, max_length=MAX_NARRATIVE_CONTENT_LENGTH * 2)

    @field_validator("content")
    @classmethod
    def _normalized(cls, value: str) -> str:
        return normalize_narrative_content(value)


class NarrativeCurrentResponse(BaseModel):
    """GET/PATCH /founder/startups/{id}/narrative: the current narrative.

    `version`/`source`/`report_id`/`input_revision` describe the immutable
    version this text physically is; `updated_at` is when the current
    pointer last moved.
    """

    model_config = ConfigDict(from_attributes=True)

    startup_id: uuid.UUID
    version: int
    content: str
    source: NarrativeSource
    report_id: uuid.UUID
    input_revision: int
    created_at: datetime
    updated_at: datetime


class NarrativeVersionResponse(BaseModel):
    """GET /founder/startups/{id}/narrative/versions/{version}: one version."""

    model_config = ConfigDict(from_attributes=True)

    version: int
    content: str
    source: NarrativeSource
    report_id: uuid.UUID
    input_revision: int
    created_at: datetime


class NarrativeVersionSummary(BaseModel):
    """One history entry: metadata and text LENGTH, never the text itself."""

    model_config = ConfigDict(from_attributes=True)

    version: int
    source: NarrativeSource
    report_id: uuid.UUID
    input_revision: int
    content_length: int
    created_at: datetime


class NarrativeVersionListResponse(BaseModel):
    """GET /founder/startups/{id}/narrative/versions: append-only history.

    Ordered by ascending version, which is the order the versions were
    written in -- `current_version` names the one a plain GET returns.
    """

    model_config = ConfigDict(from_attributes=True)

    current_version: int
    versions: list[NarrativeVersionSummary]
