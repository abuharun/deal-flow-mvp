"""Request/response contracts for the founder-editable pitch narrative.

The MVP stores ONE free-text narrative per startup; the founder chooses the
language it is written in, so nothing here is keyed by (or validated
against) a UI locale. What IS enforced: the payload is length-bounded before
any database work, blank saves are refused, browser line endings are
normalized rather than rejected, and no control characters can ever reach
the column's CHECK constraint. The history projection deliberately carries
no content -- listing versions must stay cheap and must not ship every
revision's full text.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.narrative import MAX_NARRATIVE_CONTENT_LENGTH
from app.schemas.narrative import (
    NarrativeCurrentResponse,
    NarrativePatchRequest,
    NarrativeVersionListResponse,
    NarrativeVersionResponse,
    NarrativeVersionSummary,
)


def _patch(content: str) -> NarrativePatchRequest:
    return NarrativePatchRequest.model_validate({"content": content})


class TestPatchRequest:
    def test_accepts_plain_narrative_text(self):
        assert _patch("We move freight across Central Asia.").content == (
            "We move freight across Central Asia."
        )

    def test_content_is_required(self):
        with pytest.raises(ValidationError):
            NarrativePatchRequest.model_validate({})

    def test_extra_fields_are_forbidden(self):
        # Notably: version/source/report_id are server-assigned provenance and
        # must never be settable by the client.
        with pytest.raises(ValidationError):
            NarrativePatchRequest.model_validate({"content": "ok", "version": 7})

    def test_explicit_null_is_refused(self):
        with pytest.raises(ValidationError):
            NarrativePatchRequest.model_validate({"content": None})

    @pytest.mark.parametrize("content", ["", "   ", "\n\n", "\t"])
    def test_blank_content_is_refused(self, content):
        with pytest.raises(ValidationError):
            _patch(content)

    def test_surrounding_whitespace_is_trimmed(self):
        assert _patch("  Our pitch.\n\n").content == "Our pitch."

    def test_content_at_the_limit_is_accepted(self):
        assert len(_patch("x" * MAX_NARRATIVE_CONTENT_LENGTH).content) == (
            MAX_NARRATIVE_CONTENT_LENGTH
        )

    def test_overlong_content_is_refused(self):
        with pytest.raises(ValidationError):
            _patch("x" * (MAX_NARRATIVE_CONTENT_LENGTH + 1))

    def test_length_is_measured_after_trimming(self):
        # A payload that only exceeds the cap because of padding is a save,
        # not a rejection -- the stored value is what must fit.
        content = f"  {'x' * MAX_NARRATIVE_CONTENT_LENGTH}  "
        assert len(_patch(content).content) == MAX_NARRATIVE_CONTENT_LENGTH

    def test_markdown_newlines_tabs_and_non_ascii_text_survive(self):
        content = "## Биз ким\n\n- Тошкент\tмаркет\n- O'zbekiston"
        assert _patch(content).content == content

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("a\r\nb", "a\nb"),
            ("a\rb", "a\nb"),
            ("a\r\n\r\nb", "a\n\nb"),
        ],
    )
    def test_browser_line_endings_are_normalized_not_rejected(self, raw, expected):
        assert _patch(raw).content == expected

    @pytest.mark.parametrize("control", ["\x00", "\x01", "\x07", "\x0b", "\x0c", "\x1f", "\x7f"])
    def test_control_characters_are_refused(self, control):
        with pytest.raises(ValidationError):
            _patch(f"before{control}after")


class TestResponseProjections:
    def test_current_response_carries_the_text_and_its_provenance(self):
        response = NarrativeCurrentResponse(
            startup_id=uuid.uuid4(),
            version=2,
            content="Our pitch.",
            source="founder_edit",
            report_id=uuid.uuid4(),
            input_revision=3,
            created_at=datetime(2026, 1, 15, tzinfo=UTC),
            updated_at=datetime(2026, 1, 16, tzinfo=UTC),
        )

        assert set(response.model_dump()) == {
            "startup_id",
            "version",
            "content",
            "source",
            "report_id",
            "input_revision",
            "created_at",
            "updated_at",
        }

    def test_version_summary_never_carries_content(self):
        summary = NarrativeVersionSummary(
            version=1,
            source="report_seed",
            report_id=uuid.uuid4(),
            input_revision=1,
            content_length=42,
            created_at=datetime(2026, 1, 15, tzinfo=UTC),
        )

        dumped = summary.model_dump()
        assert "content" not in dumped
        assert dumped["content_length"] == 42

    def test_version_response_carries_content(self):
        response = NarrativeVersionResponse(
            version=1,
            content="Seeded from the report.",
            source="report_seed",
            report_id=uuid.uuid4(),
            input_revision=1,
            created_at=datetime(2026, 1, 15, tzinfo=UTC),
        )

        assert response.content == "Seeded from the report."

    def test_version_list_response_names_the_current_version(self):
        response = NarrativeVersionListResponse(current_version=1, versions=[])

        assert response.current_version == 1
        assert response.versions == []
