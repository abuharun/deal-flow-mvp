"""report.v1: the strict, cited AI-research-report domain schema.

This is the ONE structured shape a future OpenAI structured-output call (or
any other provider) must produce, validated here before a single DB write
happens. `ReportBody` is exactly what lands in `analysis_reports.report`
JSONB; `SourceInput` entries become normalized `report_sources` rows keyed by
their 1-based position in `ReportV1Input.sources` (the "ordinal" that every
citation_id in the body references) -- see app.models.analysis_report.

Product contract enforced here (not just documented):
- No numeric investment score/rating and no model-generated recommend/pass/
  decision field, anywhere in the structure -- `_reject_forbidden_keys`
  recursively scans the raw input before any field parses, in addition to
  `extra="forbid"` on every nested model.
- A claim with support="cited" must carry at least one citation_id; a claim
  with any other support value must carry NONE (a non-cited claim can never
  imply source backing it doesn't have).
- Each of the three core sections must cite at least one source.
- Every citation_id anywhere in the body must resolve to a source ordinal
  that is actually present in `sources`.
- Pilot minimum evidence policy: a report must cite at least
  MIN_SOURCES (3) independent sources overall -- chosen as the smallest
  number that lets uzbekistan_central_asia_market, global_competitors, and
  us_vc_readiness each stand on distinct evidence rather than one shared
  citation propped under all three.
- Every string/list is length-bounded, and the serialized report body is
  capped at MAX_REPORT_BODY_JSON_BYTES, to keep JSONB storage and in-memory
  parsing bounded regardless of what a provider returns.
- Never chain-of-thought, hidden prompts, or raw provider payloads: there is
  no field here that could carry either (no free-form "reasoning" field, no
  passthrough dict).
"""

import json
import uuid
from collections.abc import Mapping
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.analysis_report import (
    CONFIDENCE_LEVELS,
    LANGUAGE_EN,
    MAX_SNIPPET_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_URL_LENGTH,
    SCHEMA_VERSION_REPORT_V1,
    SOURCE_QUALITIES,
)
from app.security.urls import normalize_safe_http_url

MAX_EXECUTIVE_SUMMARY_LENGTH = 4000
MAX_SECTION_NARRATIVE_LENGTH = 3000
MAX_CITATION_IDS_PER_ITEM = 10

MAX_COMPETITORS = 15
MAX_COMPETITOR_NAME_LENGTH = 200
MAX_COMPETITOR_REGION_LENGTH = 100
MAX_COMPETITOR_NOTE_LENGTH = 500

MAX_CLAIMS = 40
MAX_CLAIM_STATEMENT_LENGTH = 500

MAX_CONTRADICTIONS = 20
MAX_CONTRADICTION_LENGTH = 500

MAX_UNSUPPORTED_CLAIMS = 20
MAX_UNSUPPORTED_CLAIM_LENGTH = 500

MAX_CHECKLIST_ITEMS = 20
MAX_CHECKLIST_ITEM_SLUG_LENGTH = 64
MAX_EVIDENCE_GAP_LENGTH = 500

MAX_PITCH_NARRATIVE_DRAFT_LENGTH = 3000

# Pilot evidence policy: documented in the module docstring above.
MIN_SOURCES = 3
MAX_SOURCES = 30

# Backstop on the serialized report BODY (excludes sources, which are
# normalized rows, not JSONB). Deliberately tighter than the theoretical
# worst-case sum of the per-field bounds above (~85KB): a real pilot report
# never needs every field at its individual max simultaneously, and this cap
# is the actual guarantee for JSONB/memory safety, not the per-field bounds.
MAX_REPORT_BODY_JSON_BYTES = 60_000

SourceQuality = Literal["primary", "reputable_media", "industry", "blog", "unknown"]
Confidence = Literal["high", "medium", "low"]
ClaimSupport = Literal["cited", "founder_provided", "assumption"]
ChecklistStatus = Literal["met", "partially_met", "not_met", "unknown"]

assert set(SourceQuality.__args__) == set(SOURCE_QUALITIES)
assert set(Confidence.__args__) == set(CONFIDENCE_LEVELS)

# Never a numeric investment score/rating, never a model-generated
# recommend/pass/decision -- see the module docstring.
FORBIDDEN_KEYS = frozenset({"investment_score", "score", "rating", "recommend", "pass", "decision"})

_CitationId = Annotated[int, Field(ge=1)]
_CitationIds = Annotated[list[_CitationId], Field(max_length=MAX_CITATION_IDS_PER_ITEM)]


def _reject_forbidden_keys(node: object, *, path: str = "$") -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if isinstance(key, str) and key.lower() in FORBIDDEN_KEYS:
                raise ValueError(
                    f"field {key!r} at {path}.{key} is not permitted in an AI research report "
                    "(no numeric score/rating and no recommend/pass/decision field)"
                )
            _reject_forbidden_keys(value, path=f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _reject_forbidden_keys(item, path=f"{path}[{index}]")


def _no_duplicate_citation_ids(value: list[int]) -> list[int]:
    if len(set(value)) != len(value):
        raise ValueError("citation_ids must not contain duplicates")
    return value


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)
    published_date: date | None = None
    accessed_date: date
    source_quality: SourceQuality
    confidence: Confidence
    snippet: str | None = Field(default=None, max_length=MAX_SNIPPET_LENGTH)

    @field_validator("url")
    @classmethod
    def _safe_url(cls, value: str) -> str:
        if len(value) > MAX_URL_LENGTH:
            raise ValueError("url is too long")
        return normalize_safe_http_url(value)


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narrative: str = Field(min_length=1, max_length=MAX_SECTION_NARRATIVE_LENGTH)
    # A core section must always cite at least one source.
    citation_ids: _CitationIds = Field(min_length=1)

    @field_validator("citation_ids")
    @classmethod
    def _dedup(cls, value: list[int]) -> list[int]:
        return _no_duplicate_citation_ids(value)


class Sections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uzbekistan_central_asia_market: Section
    global_competitors: Section
    us_vc_readiness: Section


class Competitor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_COMPETITOR_NAME_LENGTH)
    region: str = Field(min_length=1, max_length=MAX_COMPETITOR_REGION_LENGTH)
    note: str = Field(default="", max_length=MAX_COMPETITOR_NOTE_LENGTH)
    citation_ids: _CitationIds = Field(default_factory=list)

    @field_validator("citation_ids")
    @classmethod
    def _dedup(cls, value: list[int]) -> list[int]:
        return _no_duplicate_citation_ids(value)


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=MAX_CLAIM_STATEMENT_LENGTH)
    support: ClaimSupport
    citation_ids: _CitationIds = Field(default_factory=list)
    confidence: Confidence

    @field_validator("citation_ids")
    @classmethod
    def _dedup(cls, value: list[int]) -> list[int]:
        return _no_duplicate_citation_ids(value)

    @model_validator(mode="after")
    def _support_matches_citations(self) -> "Claim":
        if self.support == "cited" and not self.citation_ids:
            raise ValueError("a claim with support='cited' must carry at least one citation_id")
        if self.support != "cited" and self.citation_ids:
            raise ValueError(
                "a claim with support != 'cited' must not carry citation_ids "
                "(it must never falsely imply source backing)"
            )
        return self


class ChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: str = Field(
        min_length=1, max_length=MAX_CHECKLIST_ITEM_SLUG_LENGTH, pattern=r"^[a-z][a-z0-9_]*$"
    )
    status: ChecklistStatus
    confidence: Confidence
    evidence: _CitationIds = Field(default_factory=list)
    evidence_gap: str | None = Field(default=None, max_length=MAX_EVIDENCE_GAP_LENGTH)

    @field_validator("evidence")
    @classmethod
    def _dedup(cls, value: list[int]) -> list[int]:
        return _no_duplicate_citation_ids(value)


_BoundedStr = Annotated[str, Field(min_length=1, max_length=500)]


class ReportBody(BaseModel):
    """Exactly what is stored in `analysis_reports.report` (JSONB)."""

    model_config = ConfigDict(extra="forbid")

    executive_summary: str = Field(min_length=1, max_length=MAX_EXECUTIVE_SUMMARY_LENGTH)
    sections: Sections
    competitors: list[Competitor] = Field(default_factory=list, max_length=MAX_COMPETITORS)
    claims: list[Claim] = Field(default_factory=list, max_length=MAX_CLAIMS)
    contradictions: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=MAX_CONTRADICTION_LENGTH)]],
        Field(max_length=MAX_CONTRADICTIONS),
    ] = Field(default_factory=list)
    unsupported_claims: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=MAX_UNSUPPORTED_CLAIM_LENGTH)]],
        Field(max_length=MAX_UNSUPPORTED_CLAIMS),
    ] = Field(default_factory=list)
    readiness_checklist: list[ChecklistItem] = Field(min_length=1, max_length=MAX_CHECKLIST_ITEMS)
    pitch_narrative_draft: str = Field(min_length=1, max_length=MAX_PITCH_NARRATIVE_DRAFT_LENGTH)

    def all_citation_ids(self) -> list[int]:
        ids: list[int] = []
        for section in (
            self.sections.uzbekistan_central_asia_market,
            self.sections.global_competitors,
            self.sections.us_vc_readiness,
        ):
            ids.extend(section.citation_ids)
        for competitor in self.competitors:
            ids.extend(competitor.citation_ids)
        for claim in self.claims:
            ids.extend(claim.citation_ids)
        for item in self.readiness_checklist:
            ids.extend(item.evidence)
        return ids


class ReportV1Input(BaseModel):
    """The full structured AI-report output: body + normalized sources.

    Validated as one unit so citation_ids can be checked against the actual
    number of sources supplied -- neither half is ever inserted without the
    other passing first.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["report.v1"] = SCHEMA_VERSION_REPORT_V1
    language: Literal["en"] = LANGUAGE_EN
    report: ReportBody
    sources: list[SourceInput] = Field(min_length=MIN_SOURCES, max_length=MAX_SOURCES)

    @model_validator(mode="before")
    @classmethod
    def _reject_forbidden_keys_anywhere(cls, data: object) -> object:
        _reject_forbidden_keys(data)
        return data

    @model_validator(mode="after")
    def _citations_resolve_to_source_ordinals(self) -> "ReportV1Input":
        n_sources = len(self.sources)
        unresolved = sorted({cid for cid in self.report.all_citation_ids() if cid > n_sources})
        if unresolved:
            raise ValueError(
                f"citation_ids reference source ordinals that don't exist: {unresolved} "
                f"(only 1..{n_sources} are valid)"
            )
        return self

    @model_validator(mode="after")
    def _bounded_serialized_size(self) -> "ReportV1Input":
        size = len(json.dumps(self.report.model_dump(mode="json"), separators=(",", ":")))
        if size > MAX_REPORT_BODY_JSON_BYTES:
            raise ValueError(
                f"serialized report body is {size} bytes, over the "
                f"{MAX_REPORT_BODY_JSON_BYTES}-byte pilot cap"
            )
        return self


class ReportSourceResponse(BaseModel):
    """One normalized `report_sources` row, safe for the founder to read."""

    model_config = ConfigDict(from_attributes=True)

    ordinal: int
    url: str
    title: str
    published_date: date | None
    accessed_date: date
    source_quality: SourceQuality
    confidence: Confidence
    snippet: str | None


class ReportDetailResponse(BaseModel):
    """Founder GET /founder/startups/{id}/report projection.

    `report` is re-validated through `ReportBody` (not passed through as a
    raw dict) so a response can never surface a key that wasn't part of the
    report.v1 shape validated at insert time -- defense in depth against
    anything unexpected ending up in the JSONB column. Only safe provenance
    (schema/language/model/prompt_version/generated_at/input_revision/
    partial/evidence_count) and the normalized sources accompany it; no
    internal job bookkeeping (attempts, error codes, timestamps) crosses this
    boundary -- that lives on the analysis job resource, not the report.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    startup_id: uuid.UUID
    schema_version: str
    language: str
    report: ReportBody
    sources: list[ReportSourceResponse]
    model: str
    prompt_version: str
    partial: bool
    evidence_count: int | None
    input_revision: int
    generated_at: datetime
    created_at: datetime
    stale: bool
