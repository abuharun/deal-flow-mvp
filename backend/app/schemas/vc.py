"""Read-only VC projections: exactly what an investor may see.

Every model here is an explicit allow-list, never a filter over a richer
object. A new column on `startups`, a new key in the report JSONB, or a new
field on an approval must be added here deliberately before it can reach an
investor -- the default for anything new is "not visible".

What is deliberately absent, and why:
- Founder identity (founder_id, approved_by) and anything that could
  identify or contact them: the pilot's investor surface is about the
  startup, not the person.
- The questionnaire answers, deck metadata/bytes/text, payment and consent
  rows, and analysis-job bookkeeping: founder-private inputs and internal
  state, none of which the founder approved for investor eyes.
- `pitch_narrative_draft` from the report body: the founder rewrote that
  draft and approved their own version, so shipping the AI's raw draft next
  to it would show investors narrative text the founder never approved. It
  is the one report.v1 field this projection drops -- see `VcReportBody`.
- Narrative version bookkeeping (narrative_version_id, report_id, source,
  input_revision) and all earlier versions: an investor reads the frozen
  text, not its history or how it came to be.
- `model`/`prompt_version` and the report/job ids: AI provenance internals.
  What survives is the provenance an investor can act on -- the schema and
  language of the report, whether it was partial, how much evidence backed
  it, when it was generated, and the citations themselves.

The report body is re-validated through the strict `ReportBody` before it is
projected (`VcReportBody.from_stored`), so a stored JSONB that somehow
carried an unexpected key fails loudly instead of forwarding it.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models import NarrativeApproval, NarrativeVersion, Startup
from app.models.analysis_report import AnalysisReport, ReportSource
from app.schemas.report import (
    MAX_CHECKLIST_ITEMS,
    MAX_CLAIMS,
    MAX_COMPETITORS,
    MAX_CONTRADICTION_LENGTH,
    MAX_CONTRADICTIONS,
    MAX_EXECUTIVE_SUMMARY_LENGTH,
    MAX_UNSUPPORTED_CLAIM_LENGTH,
    MAX_UNSUPPORTED_CLAIMS,
    ChecklistItem,
    Claim,
    Competitor,
    ReportBody,
    ReportSourceResponse,
    Sections,
)

# The one report.v1 field an investor never sees (see the module docstring).
DROPPED_REPORT_FIELDS = ("pitch_narrative_draft",)

# Deterministic, bounded paging. The offset cap keeps a hostile or buggy
# client from asking Postgres to walk an unbounded number of rows.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
MAX_PAGE_OFFSET = 10_000


class VcStartupSummary(BaseModel):
    """The safe startup profile: what it is, and since when it is visible."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    one_liner: str
    sector: str
    funding_stage: str
    city: str
    vc_visible_at: datetime
    approved_at: datetime

    @classmethod
    def from_row(cls, startup: Startup, *, approved_at: datetime) -> "VcStartupSummary":
        # Field by field on purpose: never `from_attributes` over the ORM
        # row, which would let a future column ride along silently.
        return cls(
            id=startup.id,
            name=startup.name,
            one_liner=startup.one_liner,
            sector=startup.sector,
            funding_stage=startup.funding_stage,
            city=startup.city,
            vc_visible_at=startup.vc_visible_at,
            approved_at=approved_at,
        )


class VcStartupListResponse(BaseModel):
    """One deterministic page plus the total behind it."""

    model_config = ConfigDict(extra="forbid")

    items: list[VcStartupSummary]
    limit: int
    offset: int
    total: int


class VcApprovedNarrative(BaseModel):
    """The frozen text the founder approved -- nothing about how it got there."""

    model_config = ConfigDict(extra="forbid")

    version: int
    content: str
    approved_at: datetime

    @classmethod
    def from_rows(
        cls, approval: NarrativeApproval, version: NarrativeVersion
    ) -> "VcApprovedNarrative":
        # The version number comes from the immutable version row; the
        # approval's composite FK guarantees the two agree.
        return cls(
            version=version.version, content=version.content, approved_at=approval.approved_at
        )


class VcReportBody(BaseModel):
    """report.v1 minus `pitch_narrative_draft`.

    Mirrors `ReportBody` field for field otherwise, so the analysis an
    investor reads -- summary, the three cited sections, competitors, claims,
    contradictions, unsupported claims, and the readiness checklist -- is the
    same immutable content the founder saw, with the same citation ids
    pointing at the same sources.
    """

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

    @classmethod
    def from_stored(cls, stored: dict) -> "VcReportBody":
        """Re-validate the stored JSONB, then drop the draft.

        `ReportBody` forbids extra keys, so anything unexpected in the column
        is refused here rather than forwarded to an investor.
        """
        body = ReportBody.model_validate(stored).model_dump(mode="json")
        for field in DROPPED_REPORT_FIELDS:
            body.pop(field, None)
        return cls.model_validate(body)


# The projection must stay a strict subset of report.v1: if a future report
# field is added, this fails at import until it is triaged here.
assert set(VcReportBody.model_fields) == set(ReportBody.model_fields) - set(DROPPED_REPORT_FIELDS)


class VcReport(BaseModel):
    """The immutable cited report as an investor reads it.

    Provenance is limited to what an investor can act on: which schema and
    language the report is in, whether generation completed fully, how many
    sources backed it, and when it was generated. The model, prompt version,
    report id, and job id stay internal.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    language: str
    report: VcReportBody
    sources: list[ReportSourceResponse]
    partial: bool
    evidence_count: int | None
    generated_at: datetime

    @classmethod
    def from_row(cls, report: AnalysisReport, sources: list[ReportSource]) -> "VcReport":
        return cls(
            schema_version=report.schema_version,
            language=report.language,
            report=VcReportBody.from_stored(report.report),
            sources=[ReportSourceResponse.model_validate(source) for source in sources],
            partial=report.partial,
            evidence_count=report.evidence_count,
            generated_at=report.generated_at,
        )


class VcStartupDossierResponse(BaseModel):
    """One approved startup: profile, frozen narrative, cited report."""

    model_config = ConfigDict(extra="forbid")

    startup: VcStartupSummary
    narrative: VcApprovedNarrative
    report: VcReport
