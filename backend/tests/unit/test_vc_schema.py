"""VC read-only projections: what an investor may see, field by field.

These are pure schema tests -- no database, no HTTP. They pin the exact
field sets of every VC-facing model, because the whole security property of
this slice is "the projection is an allow-list, not a filter": a new column
on `startups`, a new key in the report JSONB, or a new approval field must
never reach an investor just because it was added upstream.

Specifically asserted here:
- The report body an investor reads is report.v1 MINUS
  `pitch_narrative_draft`: the founder approved their own edited narrative,
  so the AI's raw draft is narrative-draft material and never ships.
- Stored JSONB is re-validated through the strict `ReportBody` before it is
  projected, so an unexpected key in the column is refused rather than
  forwarded.
- No VC model carries founder identity (`founder_id`, `approved_by`),
  questionnaire answers, provenance internals (`model`, `prompt_version`,
  `job_id`, `report_id`, `input_revision`), or narrative bookkeeping
  (`narrative_version_id`, `source`).
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import NarrativeApproval, NarrativeVersion, Startup, StartupStatus
from app.models.analysis_report import AnalysisReport, ReportSource
from app.schemas.report import ReportBody
from app.schemas.vc import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    VcApprovedNarrative,
    VcReport,
    VcReportBody,
    VcStartupDossierResponse,
    VcStartupListResponse,
    VcStartupSummary,
)

APPROVED_AT = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
VISIBLE_AT = datetime(2026, 2, 1, 8, 59, tzinfo=UTC)
GENERATED_AT = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

# Names that must never appear as a field on any VC-facing model.
FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "founder_id",
        "approved_by",
        "created_by",
        "email",
        "user_id",
        "narrative_version_id",
        "report_id",
        "job_id",
        "input_revision",
        "model",
        "prompt_version",
        "pitch_narrative_draft",
        "source",
        "submission",
        "problem",
        "product",
        "market",
        "traction",
        "team",
        "ask",
        "ask_amount",
        "revenue",
        "growth",
        "dataroom_url",
        "stale",
        "password_hash",
        "token",
    }
)


def report_body_payload(**overrides) -> dict:
    payload = {
        "executive_summary": "A concise summary of the startup.",
        "sections": {
            "uzbekistan_central_asia_market": {
                "narrative": "Central Asia market narrative.",
                "citation_ids": [1],
            },
            "global_competitors": {
                "narrative": "Global competitor narrative.",
                "citation_ids": [2],
            },
            "us_vc_readiness": {
                "narrative": "US VC readiness narrative.",
                "citation_ids": [3],
            },
        },
        "competitors": [
            {"name": "Acme Corp", "region": "US", "note": "similar product", "citation_ids": [1]}
        ],
        "claims": [
            {
                "statement": "The market is growing quickly.",
                "support": "cited",
                "citation_ids": [1],
                "confidence": "medium",
            }
        ],
        "contradictions": ["Two sources disagree on market size."],
        "unsupported_claims": ["Revenue growth could not be verified."],
        "readiness_checklist": [
            {
                "item": "data_room",
                "status": "unknown",
                "confidence": "low",
                "evidence": [],
                "evidence_gap": "no data room shared yet",
            }
        ],
        "pitch_narrative_draft": "The AI's raw draft the founder rewrote.",
    }
    payload.update(overrides)
    return payload


def startup_row(**overrides) -> Startup:
    values = {
        "id": uuid.uuid4(),
        "founder_id": uuid.uuid4(),
        "name": "Yuk Express",
        "one_liner": "Freight matching for Central Asia.",
        "sector": "logistics",
        "funding_stage": "seed",
        "city": "Tashkent",
        "status": StartupStatus.VC_VISIBLE,
        "input_revision": 4,
        "vc_visible_at": VISIBLE_AT,
    }
    values.update(overrides)
    return Startup(**values)


def report_row(**overrides) -> AnalysisReport:
    values = {
        "id": uuid.uuid4(),
        "startup_id": uuid.uuid4(),
        "job_id": uuid.uuid4(),
        "input_revision": 4,
        "schema_version": "report.v1",
        "language": "en",
        "report": report_body_payload(),
        "model": "gpt-test",
        "prompt_version": "v1",
        "partial": False,
        "evidence_count": 3,
        "generated_at": GENERATED_AT,
    }
    values.update(overrides)
    return AnalysisReport(**values)


def source_row(ordinal: int) -> ReportSource:
    return ReportSource(
        id=uuid.uuid4(),
        report_id=uuid.uuid4(),
        ordinal=ordinal,
        url=f"https://example.com/article-{ordinal}",
        title=f"Article {ordinal}",
        published_date=None,
        accessed_date=GENERATED_AT.date(),
        source_quality="reputable_media",
        confidence="medium",
        snippet=None,
    )


class TestVcReportBody:
    def test_drops_the_pitch_narrative_draft(self):
        body = VcReportBody.from_stored(report_body_payload())

        assert "pitch_narrative_draft" not in body.model_dump()
        assert "pitch_narrative_draft" not in VcReportBody.model_fields

    def test_keeps_every_other_report_v1_field(self):
        expected = set(ReportBody.model_fields) - {"pitch_narrative_draft"}

        assert set(VcReportBody.model_fields) == expected

    def test_preserves_the_analysis_content_verbatim(self):
        body = VcReportBody.from_stored(report_body_payload())

        assert body.executive_summary == "A concise summary of the startup."
        assert body.sections.global_competitors.citation_ids == [2]
        assert body.competitors[0].name == "Acme Corp"
        assert body.claims[0].support == "cited"
        assert body.contradictions == ["Two sources disagree on market size."]
        assert body.unsupported_claims == ["Revenue growth could not be verified."]
        assert body.readiness_checklist[0].item == "data_room"

    def test_stored_json_is_revalidated_so_an_unexpected_key_is_refused(self):
        payload = report_body_payload()
        payload["leaked_founder_note"] = "private"

        with pytest.raises(ValidationError):
            VcReportBody.from_stored(payload)

    def test_a_draft_supplied_directly_is_refused_rather_than_ignored(self):
        with pytest.raises(ValidationError):
            VcReportBody.model_validate(report_body_payload())

    def test_a_stored_body_missing_the_draft_is_refused_not_partially_read(self):
        # ReportBody requires the draft, so a stored body without one is not a
        # valid report.v1 row: the failure is loud rather than a partial read.
        payload = report_body_payload()
        payload.pop("pitch_narrative_draft")

        with pytest.raises(ValidationError):
            VcReportBody.from_stored(payload)


class TestVcStartupSummary:
    def test_exposes_only_safe_profile_fields(self):
        assert set(VcStartupSummary.model_fields) == {
            "id",
            "name",
            "one_liner",
            "sector",
            "funding_stage",
            "city",
            "vc_visible_at",
            "approved_at",
        }

    def test_from_row_never_copies_founder_identity_or_bookkeeping(self):
        startup = startup_row()

        summary = VcStartupSummary.from_row(startup, approved_at=APPROVED_AT)
        dumped = summary.model_dump()

        assert dumped["id"] == startup.id
        assert dumped["name"] == "Yuk Express"
        assert dumped["approved_at"] == APPROVED_AT
        assert dumped["vc_visible_at"] == VISIBLE_AT
        assert str(startup.founder_id) not in str(dumped)
        assert "input_revision" not in dumped
        assert "status" not in dumped


class TestVcApprovedNarrative:
    def test_exposes_only_the_frozen_text_and_when_it_was_approved(self):
        assert set(VcApprovedNarrative.model_fields) == {"version", "content", "approved_at"}

    def test_from_rows_carries_the_approved_version_text(self):
        version = NarrativeVersion(
            id=uuid.uuid4(),
            startup_id=uuid.uuid4(),
            version=3,
            content="The founder's own approved pitch.",
            source="founder_edit",
            report_id=uuid.uuid4(),
            input_revision=4,
            created_by=uuid.uuid4(),
        )
        approval = NarrativeApproval(
            id=uuid.uuid4(),
            startup_id=version.startup_id,
            narrative_version_id=version.id,
            version=version.version,
            report_id=version.report_id,
            approved_by=uuid.uuid4(),
            approved_at=APPROVED_AT,
        )

        narrative = VcApprovedNarrative.from_rows(approval, version)

        assert narrative.model_dump() == {
            "version": 3,
            "content": "The founder's own approved pitch.",
            "approved_at": APPROVED_AT,
        }
        assert str(approval.approved_by) not in str(narrative.model_dump())


class TestVcReport:
    def test_exposes_only_safe_provenance(self):
        assert set(VcReport.model_fields) == {
            "schema_version",
            "language",
            "report",
            "sources",
            "partial",
            "evidence_count",
            "generated_at",
        }

    def test_from_row_projects_body_and_sources_in_ordinal_order(self):
        report = report_row()
        sources = [source_row(1), source_row(2), source_row(3)]

        projected = VcReport.from_row(report, sources)

        assert projected.schema_version == "report.v1"
        assert projected.language == "en"
        assert projected.partial is False
        assert projected.evidence_count == 3
        assert projected.generated_at == GENERATED_AT
        assert [source.ordinal for source in projected.sources] == [1, 2, 3]
        assert "pitch_narrative_draft" not in projected.model_dump()["report"]

    def test_never_carries_model_or_job_provenance(self):
        projected = VcReport.from_row(report_row(), [source_row(1)])
        dumped = str(projected.model_dump())

        assert "gpt-test" not in dumped
        assert "prompt_version" not in dumped


class TestDossierAndListEnvelopes:
    def test_dossier_is_exactly_profile_narrative_and_report(self):
        assert set(VcStartupDossierResponse.model_fields) == {"startup", "narrative", "report"}

    def test_list_envelope_carries_deterministic_pagination_metadata(self):
        assert set(VcStartupListResponse.model_fields) == {"items", "limit", "offset", "total"}

    def test_page_size_bounds_are_defined_and_sane(self):
        assert 1 <= DEFAULT_PAGE_SIZE <= MAX_PAGE_SIZE

    @pytest.mark.parametrize(
        "model",
        [VcStartupSummary, VcApprovedNarrative, VcReport, VcStartupDossierResponse, VcReportBody],
    )
    def test_no_vc_model_declares_a_forbidden_field(self, model):
        assert not (set(model.model_fields) & FORBIDDEN_FIELD_NAMES)

    @pytest.mark.parametrize(
        "model",
        [VcStartupSummary, VcApprovedNarrative, VcReport, VcStartupDossierResponse, VcReportBody],
    )
    def test_every_vc_model_forbids_extra_fields(self, model):
        assert model.model_config.get("extra") == "forbid"
