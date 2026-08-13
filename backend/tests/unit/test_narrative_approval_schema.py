"""Request/response contracts for founder approval of the pitch narrative.

The request is deliberately minimal and deliberately explicit: exactly one
field, the version number the founder is looking at. Everything about who
approved, when, and what the startup becomes is server-assigned, so a client
can neither backdate an approval nor claim someone else made it.

The response must carry the frozen text itself (the founder is entitled to
see precisely what an investor will read) and the resulting locked state --
and must not carry any recipient or delivery field, which is future work.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.narrative_approval import (
    MAX_VERSION_NUMBER,
    NarrativeApprovalRequest,
    NarrativeApprovalResponse,
)


def _response_payload(**overrides) -> dict:
    payload = {
        "startup_id": uuid.uuid4(),
        "narrative_version_id": uuid.uuid4(),
        "version": 2,
        "content": "## Biz kimmiz\n\nToshkentda yuk tashishni raqamlashtiramiz.",
        "source": "founder_edit",
        "report_id": uuid.uuid4(),
        "input_revision": 3,
        "approved_by": uuid.uuid4(),
        "approved_at": datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
        "status": "vc_visible",
        "vc_visible_at": datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
    }
    payload.update(overrides)
    return payload


class TestApprovalRequest:
    def test_accepts_a_version_number(self):
        assert NarrativeApprovalRequest.model_validate({"version": 3}).version == 3

    def test_version_is_required(self):
        # Approval must name what it freezes; "whatever is current" would let
        # an edit made in another tab be approved unseen.
        with pytest.raises(ValidationError):
            NarrativeApprovalRequest.model_validate({})

    @pytest.mark.parametrize("version", [0, -1, "two", 1.5, None])
    def test_malformed_versions_are_refused(self, version):
        with pytest.raises(ValidationError):
            NarrativeApprovalRequest.model_validate({"version": version})

    def test_the_highest_storable_version_is_accepted(self):
        assert (
            NarrativeApprovalRequest.model_validate({"version": MAX_VERSION_NUMBER}).version
            == MAX_VERSION_NUMBER
        )

    def test_a_version_beyond_the_column_is_a_validation_error_not_a_database_error(self):
        with pytest.raises(ValidationError):
            NarrativeApprovalRequest.model_validate({"version": MAX_VERSION_NUMBER + 1})

    @pytest.mark.parametrize(
        "extra",
        [
            {"approved_by": str(uuid.uuid4())},
            {"approved_at": "2020-01-01T00:00:00Z"},
            {"content": "text the client made up"},
            {"status": "vc_visible"},
        ],
    )
    def test_server_assigned_fields_are_refused(self, extra):
        with pytest.raises(ValidationError):
            NarrativeApprovalRequest.model_validate({"version": 1, **extra})


class TestApprovalResponse:
    def test_projects_the_frozen_version_and_the_resulting_lock(self):
        payload = _response_payload()

        response = NarrativeApprovalResponse.model_validate(payload)

        assert response.version == 2
        assert response.content == payload["content"]
        assert response.source == "founder_edit"
        assert response.status.value == "vc_visible"
        assert response.vc_visible_at == payload["vc_visible_at"]

    def test_the_approved_text_is_carried_verbatim(self):
        # Non-ASCII, newlines and markdown all survive: the founder must see
        # exactly the text that was frozen.
        content = "## Кто мы\n\n- Ташкент\tрынок\n- Растём"

        response = NarrativeApprovalResponse.model_validate(_response_payload(content=content))

        assert response.content == content

    def test_an_unknown_source_is_refused(self):
        with pytest.raises(ValidationError):
            NarrativeApprovalResponse.model_validate(_response_payload(source="manual"))

    def test_the_response_carries_no_recipient_or_delivery_field(self):
        fields = set(NarrativeApprovalResponse.model_fields)
        assert not fields & {"sent_at", "recipient_id", "recipients", "audience", "delivered_at"}
