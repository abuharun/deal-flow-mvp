"""Unit tests for the report.v1 domain schema (app.schemas.report).

Covers the product contract the schema must enforce BEFORE a single DB
write: forbidden numeric-score/decision fields (top-level and nested),
unknown fields, citation_id/support consistency, citation_ids resolving to
an actual source ordinal, per-core-section citation requirement, the pilot
minimum-evidence policy, safe source URLs, and bounded string/list sizes
(including the aggregate serialized-size cap). No network, no OpenAI, no DB
-- pure schema-level validation.
"""

import copy
import json

import pytest
from pydantic import ValidationError

from app.schemas.report import (
    MAX_CHECKLIST_ITEMS,
    MAX_CLAIM_STATEMENT_LENGTH,
    MAX_CLAIMS,
    MAX_COMPETITOR_NAME_LENGTH,
    MAX_COMPETITORS,
    MAX_CONTRADICTIONS,
    MAX_EXECUTIVE_SUMMARY_LENGTH,
    MAX_REPORT_BODY_JSON_BYTES,
    MAX_SECTION_NARRATIVE_LENGTH,
    MAX_SOURCES,
    MIN_SOURCES,
    ReportV1Input,
)


def _source(ordinal_hint: int = 1, **overrides) -> dict:
    values = {
        "url": f"https://example.com/article-{ordinal_hint}",
        "title": f"Article {ordinal_hint}",
        "accessed_date": "2026-01-01",
        "source_quality": "reputable_media",
        "confidence": "medium",
    }
    values.update(overrides)
    return values


def _section(citation_ids: list[int] | None = None, narrative: str = "narrative text") -> dict:
    return {"narrative": narrative, "citation_ids": [] if citation_ids is None else citation_ids}


def _valid_payload() -> dict:
    return {
        "schema_version": "report.v1",
        "language": "en",
        "report": {
            "executive_summary": "A concise executive summary.",
            "sections": {
                "uzbekistan_central_asia_market": _section([1]),
                "global_competitors": _section([2]),
                "us_vc_readiness": _section([3]),
            },
            "competitors": [
                {
                    "name": "Acme Corp",
                    "region": "US",
                    "note": "similar product",
                    "citation_ids": [1],
                }
            ],
            "claims": [
                {
                    "statement": "The market is growing.",
                    "support": "cited",
                    "citation_ids": [1],
                    "confidence": "medium",
                },
                {
                    "statement": "Founder says revenue is $10k MRR.",
                    "support": "founder_provided",
                    "citation_ids": [],
                    "confidence": "low",
                },
            ],
            "contradictions": [],
            "unsupported_claims": [],
            "readiness_checklist": [
                {
                    "item": "data_room",
                    "status": "unknown",
                    "confidence": "low",
                    "evidence": [],
                    "evidence_gap": "no data room shared yet",
                }
            ],
            "pitch_narrative_draft": "Draft narrative for the founder to edit later.",
        },
        "sources": [_source(1), _source(2), _source(3)],
    }


def test_valid_minimal_payload_parses():
    parsed = ReportV1Input.model_validate(_valid_payload())
    assert parsed.schema_version == "report.v1"
    assert parsed.language == "en"
    assert len(parsed.sources) == 3
    assert parsed.report.sections.uzbekistan_central_asia_market.citation_ids == [1]


class TestUnknownFields:
    def test_unknown_top_level_field_is_rejected(self):
        payload = _valid_payload()
        payload["unexpected"] = "value"
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_unknown_field_nested_in_report_body_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["unexpected"] = "value"
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_unknown_field_nested_in_a_claim_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["claims"][0]["unexpected"] = "value"
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_unknown_field_nested_in_a_source_is_rejected(self):
        payload = _valid_payload()
        payload["sources"][0]["unexpected"] = "value"
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)


class TestForbiddenScoreAndDecisionFields:
    @pytest.mark.parametrize(
        "key", ["investment_score", "score", "rating", "recommend", "pass", "decision"]
    )
    def test_forbidden_key_at_top_level_is_rejected(self, key):
        payload = _valid_payload()
        payload[key] = 8
        with pytest.raises(ValidationError, match=key):
            ReportV1Input.model_validate(payload)

    @pytest.mark.parametrize(
        "key", ["investment_score", "score", "rating", "recommend", "pass", "decision"]
    )
    def test_forbidden_key_nested_in_report_body_is_rejected(self, key):
        payload = _valid_payload()
        payload["report"][key] = 8
        with pytest.raises(ValidationError, match=key):
            ReportV1Input.model_validate(payload)

    @pytest.mark.parametrize(
        "key", ["investment_score", "score", "rating", "recommend", "pass", "decision"]
    )
    def test_forbidden_key_nested_inside_a_claim_is_rejected(self, key):
        payload = _valid_payload()
        payload["report"]["claims"][0][key] = 8
        with pytest.raises(ValidationError, match=key):
            ReportV1Input.model_validate(payload)

    @pytest.mark.parametrize(
        "key", ["investment_score", "score", "rating", "recommend", "pass", "decision"]
    )
    def test_forbidden_key_nested_inside_a_source_is_rejected(self, key):
        payload = _valid_payload()
        payload["sources"][0][key] = 8
        with pytest.raises(ValidationError, match=key):
            ReportV1Input.model_validate(payload)

    def test_forbidden_key_case_insensitive(self):
        payload = _valid_payload()
        payload["Investment_Score"] = 9
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)


class TestClaimSupportCitationConsistency:
    def test_cited_claim_without_citations_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["claims"][0]["citation_ids"] = []
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    @pytest.mark.parametrize("support", ["founder_provided", "assumption"])
    def test_non_cited_claim_with_citations_is_rejected(self, support):
        payload = _valid_payload()
        payload["report"]["claims"][1]["support"] = support
        payload["report"]["claims"][1]["citation_ids"] = [1]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_non_cited_claim_without_citations_is_accepted(self):
        payload = _valid_payload()
        parsed = ReportV1Input.model_validate(payload)
        assert parsed.report.claims[1].support == "founder_provided"
        assert parsed.report.claims[1].citation_ids == []


class TestCoreSectionsRequireCitations:
    @pytest.mark.parametrize(
        "section_key",
        ["uzbekistan_central_asia_market", "global_competitors", "us_vc_readiness"],
    )
    def test_core_section_without_citations_is_rejected(self, section_key):
        payload = _valid_payload()
        payload["report"]["sections"][section_key]["citation_ids"] = []
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_missing_core_section_is_rejected(self):
        payload = _valid_payload()
        del payload["report"]["sections"]["us_vc_readiness"]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)


class TestCitationIdsResolveToSourceOrdinals:
    def test_citation_id_beyond_source_count_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["sections"]["us_vc_readiness"]["citation_ids"] = [99]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_citation_id_zero_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["sections"]["us_vc_readiness"]["citation_ids"] = [0]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_negative_citation_id_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["sections"]["us_vc_readiness"]["citation_ids"] = [-1]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_duplicate_citation_ids_in_one_item_are_rejected(self):
        payload = _valid_payload()
        payload["report"]["sections"]["us_vc_readiness"]["citation_ids"] = [3, 3]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_readiness_checklist_evidence_beyond_source_count_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["readiness_checklist"][0]["evidence"] = [42]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_competitor_citation_beyond_source_count_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["competitors"][0]["citation_ids"] = [42]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)


class TestMinimumEvidencePolicy:
    def test_fewer_than_minimum_sources_is_rejected(self):
        payload = _valid_payload()
        payload["sources"] = payload["sources"][: MIN_SOURCES - 1]
        # Also drop citations that would now be out of range.
        payload["report"]["sections"]["us_vc_readiness"]["citation_ids"] = [1]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_minimum_sources_is_accepted(self):
        payload = _valid_payload()
        assert len(payload["sources"]) == MIN_SOURCES
        ReportV1Input.model_validate(payload)

    def test_more_than_max_sources_is_rejected(self):
        payload = _valid_payload()
        payload["sources"] = [_source(i) for i in range(1, MAX_SOURCES + 2)]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)


class TestSourceUrlSafety:
    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "ftp://files.example.com/room",
            "https://user:pass@example.com/room",
            "https://example.com/folder#fragment",
            "https://example.com/fol der",
            "not a url",
            "",
        ],
    )
    def test_unsafe_source_url_is_rejected(self, url):
        payload = _valid_payload()
        payload["sources"][0]["url"] = url
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_safe_url_is_normalized(self):
        payload = _valid_payload()
        payload["sources"][0]["url"] = "HTTPS://Example.COM/Article?x=1"
        parsed = ReportV1Input.model_validate(payload)
        assert parsed.sources[0].url == "https://example.com/Article?x=1"

    def test_overlong_url_is_rejected(self):
        payload = _valid_payload()
        payload["sources"][0]["url"] = "https://example.com/" + "a" * 2048
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)


class TestSourceFieldBounds:
    @pytest.mark.parametrize("value", ["", "x" * 301])
    def test_title_length_bounds(self, value):
        payload = _valid_payload()
        payload["sources"][0]["title"] = value
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_snippet_over_limit_is_rejected(self):
        payload = _valid_payload()
        payload["sources"][0]["snippet"] = "x" * 1001
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    @pytest.mark.parametrize("value", ["", "PRIMARY", "official"])
    def test_source_quality_must_be_canonical(self, value):
        payload = _valid_payload()
        payload["sources"][0]["source_quality"] = value
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    @pytest.mark.parametrize("value", ["", "HIGH", "certain"])
    def test_confidence_must_be_canonical(self, value):
        payload = _valid_payload()
        payload["sources"][0]["confidence"] = value
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)


class TestSchemaVersionAndLanguage:
    def test_wrong_schema_version_is_rejected(self):
        payload = _valid_payload()
        payload["schema_version"] = "report.v2"
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_unsupported_language_is_rejected(self):
        payload = _valid_payload()
        payload["language"] = "ru"
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)


class TestBoundedStringsAndLists:
    def test_executive_summary_over_limit_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["executive_summary"] = "x" * (MAX_EXECUTIVE_SUMMARY_LENGTH + 1)
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_section_narrative_over_limit_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["sections"]["us_vc_readiness"]["narrative"] = "x" * (
            MAX_SECTION_NARRATIVE_LENGTH + 1
        )
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_claim_statement_over_limit_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["claims"][0]["statement"] = "x" * (MAX_CLAIM_STATEMENT_LENGTH + 1)
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_competitor_name_over_limit_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["competitors"][0]["name"] = "x" * (MAX_COMPETITOR_NAME_LENGTH + 1)
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_too_many_competitors_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["competitors"] = [
            {"name": f"Co {i}", "region": "US", "note": "", "citation_ids": []}
            for i in range(MAX_COMPETITORS + 1)
        ]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_too_many_claims_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["claims"] = [
            {
                "statement": f"Claim {i}",
                "support": "assumption",
                "citation_ids": [],
                "confidence": "low",
            }
            for i in range(MAX_CLAIMS + 1)
        ]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_too_many_contradictions_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["contradictions"] = [
            f"contradiction {i}" for i in range(MAX_CONTRADICTIONS + 1)
        ]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_too_many_checklist_items_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["readiness_checklist"] = [
            {
                "item": f"item_{i}",
                "status": "unknown",
                "confidence": "low",
                "evidence": [],
                "evidence_gap": None,
            }
            for i in range(MAX_CHECKLIST_ITEMS + 1)
        ]
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_empty_readiness_checklist_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["readiness_checklist"] = []
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_checklist_item_slug_must_match_pattern(self):
        payload = _valid_payload()
        payload["report"]["readiness_checklist"][0]["item"] = "Not A Slug!"
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_checklist_status_must_be_canonical(self):
        payload = _valid_payload()
        payload["report"]["readiness_checklist"][0]["status"] = "maybe"
        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)


class TestAggregateSerializedSizeCap:
    def test_worst_case_bounded_payload_exceeds_the_cap_and_is_rejected(self):
        payload = _valid_payload()
        payload["report"]["executive_summary"] = "x" * MAX_EXECUTIVE_SUMMARY_LENGTH
        for key in payload["report"]["sections"]:
            payload["report"]["sections"][key]["narrative"] = "x" * MAX_SECTION_NARRATIVE_LENGTH
        payload["report"]["competitors"] = [
            {
                "name": "x" * MAX_COMPETITOR_NAME_LENGTH,
                "region": "x" * 100,
                "note": "x" * 500,
                "citation_ids": [1],
            }
            for _ in range(MAX_COMPETITORS)
        ]
        payload["report"]["claims"] = [
            {
                "statement": "x" * MAX_CLAIM_STATEMENT_LENGTH,
                "support": "cited",
                "citation_ids": [1],
                "confidence": "high",
            }
            for _ in range(MAX_CLAIMS)
        ]
        payload["report"]["contradictions"] = ["x" * 500 for _ in range(MAX_CONTRADICTIONS)]
        payload["report"]["unsupported_claims"] = ["x" * 500 for _ in range(20)]
        payload["report"]["readiness_checklist"] = [
            {
                "item": f"item_{i}",
                "status": "unknown",
                "confidence": "low",
                "evidence": [1],
                "evidence_gap": "x" * 500,
            }
            for i in range(MAX_CHECKLIST_ITEMS)
        ]
        payload["report"]["pitch_narrative_draft"] = "x" * 3000

        # Sanity: this deliberately-maximal body really is over the cap.
        raw_size = len(json.dumps(payload["report"]))
        assert raw_size > MAX_REPORT_BODY_JSON_BYTES

        with pytest.raises(ValidationError):
            ReportV1Input.model_validate(payload)

    def test_small_valid_payload_is_well_under_the_cap(self):
        payload = _valid_payload()
        parsed = ReportV1Input.model_validate(payload)
        size = len(json.dumps(parsed.report.model_dump(mode="json")))
        assert size < MAX_REPORT_BODY_JSON_BYTES


class TestDeepCopyIsolation:
    def test_valid_payload_helper_is_not_mutated_between_tests(self):
        # Regression guard for the copy-per-test pattern above.
        first = _valid_payload()
        second = copy.deepcopy(first)
        first["report"]["claims"][0]["statement"] = "mutated"
        assert second["report"]["claims"][0]["statement"] != "mutated"
