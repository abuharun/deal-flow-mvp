"""Founder approval: freezing one narrative version and going VC-visible.

Product contract under test: a startup becomes visible to investors only
because its founder explicitly said so, and what gets frozen is the exact
version the founder named -- not "whatever is current when the request
lands". Approval records which version, who approved it, and when, and in the
same transaction locks the startup; from then on that text is immutable and
every founder mutation answers the canonical 409 STARTUP_LOCKED.

Also asserted here:
- Preconditions are real: no completed report, or a narrative that was never
  materialized, answers 409 NARRATIVE_NOT_READY and writes nothing. Approval
  never seeds the narrative -- the founder must have read it first.
- Naming a version that is not current answers 409
  NARRATIVE_VERSION_MISMATCH and changes nothing, so an autosave from another
  tab can never be approved unseen.
- Re-approving the SAME version is idempotent: same body, one approval row,
  one audit event. Approving a DIFFERENT version afterwards is STARTUP_LOCKED
  and leaves the original approval intact.
- The approved version stays exactly retrievable even though earlier
  revisions exist in history.
- Access control mirrors every other founder-startup route, and the mutation
  demands an exact allowed Origin while the read stays origin-free.
- Audit rows carry IDs and version numbers only -- never a character of the
  narrative or of the report.
- Nothing is sent and no recipient is assigned: approval is a freeze plus
  visibility, and the audience policy is deliberately future work.
"""

import uuid

import pytest

from app.db import build_engine
from tests.integration.test_founder_analysis import run_sql, trigger
from tests.integration.test_founder_narrative import (
    FOUNDER_TEXT,
    FOUNDER_TEXT_2,
    SEED_DRAFT,
    get_narrative,
    get_version,
    list_versions,
    save_narrative,
    startup_with_report,
    version_rows,
)
from tests.integration.test_founder_startups import (
    COMPLETE_ANSWERS,
    assert_error_envelope,
    create_startup,
    fetch_all,
    founder_headers,
    open_client,
    seed_user,
)

APPROVAL = "/founder/startups/{}/narrative/approval"
NARRATIVE = "/founder/startups/{}/narrative"
STARTUPS = "/founder/startups"
ANALYSIS = "/founder/startups/{}/analysis"
ORIGIN = "http://localhost:5173"

EXPECTED_RESPONSE_KEYS = {
    "startup_id",
    "narrative_version_id",
    "version",
    "content",
    "source",
    "report_id",
    "input_revision",
    "approved_by",
    "approved_at",
    "status",
    "vc_visible_at",
}


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def client(test_database_url, db_at_head):
    async with open_client(test_database_url) as c:
        yield c


async def approve(
    client, token: str, startup_id: str, version, *, origin: str | None = ORIGIN, **extra
):
    return await client.post(
        APPROVAL.format(startup_id),
        json={"version": version, **extra},
        headers=founder_headers(token, origin=origin),
    )


async def get_approval(client, token: str, startup_id: str, *, origin: str | None = None):
    return await client.get(
        APPROVAL.format(startup_id), headers=founder_headers(token, origin=origin)
    )


async def approval_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT version, narrative_version_id::text AS narrative_version_id, "
        "report_id::text AS report_id, approved_by::text AS approved_by, approved_at "
        "FROM narrative_approvals WHERE startup_id = :sid",
        sid=startup_id,
    )


async def approval_audit_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT action, actor_id::text AS actor_id, metadata::text AS metadata_text "
        "FROM audit_log WHERE entity_id = :sid AND action = 'startup.narrative_approved' "
        "ORDER BY at, id",
        sid=startup_id,
    )


async def startup_row(engine, startup_id: str) -> dict:
    rows = await fetch_all(
        engine,
        "SELECT status::text AS status, vc_visible_at, input_revision "
        "FROM startups WHERE id = :sid",
        sid=startup_id,
    )
    return rows[0]


async def read_narrative(client, token: str, startup_id: str):
    """Materialize the narrative and return the current (version, content)."""
    response = await get_narrative(client, token, startup_id)
    assert response.status_code == 200, response.text
    return response.json()


async def edited_narrative(client, engine, token: str, content: str = FOUNDER_TEXT):
    """A startup whose narrative has been edited once -- version 2 is current."""
    startup, report = await startup_with_report(client, engine, token)
    saved = await save_narrative(client, token, startup["id"], content)
    assert saved.status_code == 200, saved.text
    return startup, report, saved.json()


class TestApproving:
    async def test_approving_the_current_version_freezes_it_and_locks_the_startup(
        self, client, engine
    ):
        founder_id, token = await seed_user(engine)
        startup, report = await startup_with_report(client, engine, token)
        current = await read_narrative(client, token, startup["id"])

        response = await approve(client, token, startup["id"], current["version"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == EXPECTED_RESPONSE_KEYS
        assert body["startup_id"] == startup["id"]
        assert body["version"] == 1
        assert body["content"] == SEED_DRAFT
        assert body["source"] == "report_seed"
        assert body["report_id"] == str(report.id)
        assert body["approved_by"] == str(founder_id)
        assert body["approved_at"]
        assert body["status"] == "vc_visible"
        assert body["vc_visible_at"]

    async def test_the_approval_row_names_the_exact_version_that_was_current(self, client, engine):
        founder_id, token = await seed_user(engine)
        startup, report, current = await edited_narrative(client, engine, token)

        await approve(client, token, startup["id"], current["version"])

        rows = await approval_rows(engine, startup["id"])
        assert len(rows) == 1
        assert rows[0]["version"] == 2
        assert rows[0]["report_id"] == str(report.id)
        assert rows[0]["approved_by"] == str(founder_id)
        assert rows[0]["approved_at"] is not None

    async def test_approving_an_edited_narrative_freezes_the_edit_not_the_seed(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup, _, current = await edited_narrative(client, engine, token)

        body = (await approve(client, token, startup["id"], current["version"])).json()

        assert body["version"] == 2
        assert body["content"] == FOUNDER_TEXT
        assert body["source"] == "founder_edit"

    async def test_the_startup_becomes_vc_visible_in_the_database_and_the_api(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        current = await read_narrative(client, token, startup["id"])

        await approve(client, token, startup["id"], current["version"])

        row = await startup_row(engine, startup["id"])
        assert row["status"] == "vc_visible"
        assert row["vc_visible_at"] is not None
        detail = await client.get(f"{STARTUPS}/{startup['id']}", headers=founder_headers(token))
        assert detail.json()["status"] == "vc_visible"
        assert detail.json()["vc_visible_at"]

    async def test_approval_does_not_bump_the_input_revision(self, client, engine):
        # Approving is not a founder-input change: it freezes what is already
        # there, so the revision the report was written against still holds.
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        current = await read_narrative(client, token, startup["id"])
        before = (await startup_row(engine, startup["id"]))["input_revision"]

        await approve(client, token, startup["id"], current["version"])

        assert (await startup_row(engine, startup["id"]))["input_revision"] == before

    async def test_approving_one_startup_leaves_the_founders_others_editable(self, client, engine):
        _, token = await seed_user(engine)
        first, _ = await startup_with_report(client, engine, token, draft="First startup draft.")
        second, _ = await startup_with_report(client, engine, token, draft="Second startup draft.")
        await read_narrative(client, token, first["id"])
        await approve(client, token, first["id"], 1)

        saved = await save_narrative(client, token, second["id"], FOUNDER_TEXT)

        assert saved.status_code == 200, saved.text
        assert (await startup_row(engine, second["id"]))["status"] != "vc_visible"
        assert await approval_rows(engine, second["id"]) == []


class TestIdempotency:
    async def test_re_approving_the_same_version_returns_the_same_body(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])
        first = await approve(client, token, startup["id"], 1)

        again = await approve(client, token, startup["id"], 1)

        assert again.status_code == 200, again.text
        assert again.json() == first.json()

    async def test_repeated_approvals_write_exactly_one_row_and_one_audit_event(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])

        for _ in range(3):
            assert (await approve(client, token, startup["id"], 1)).status_code == 200

        assert len(await approval_rows(engine, startup["id"])) == 1
        assert len(await approval_audit_rows(engine, startup["id"])) == 1

    async def test_the_frozen_timestamp_never_moves_on_a_repeat(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])
        first = (await approve(client, token, startup["id"], 1)).json()

        again = (await approve(client, token, startup["id"], 1)).json()

        assert again["approved_at"] == first["approved_at"]
        assert again["vc_visible_at"] == first["vc_visible_at"]


class TestVersionMismatch:
    async def test_approving_a_stale_version_is_refused_and_writes_nothing(self, client, engine):
        # The founder is looking at version 1 while an autosave in another tab
        # already wrote version 2; freezing v1 would publish text nobody
        # re-read, and freezing v2 would publish text nobody approved.
        _, token = await seed_user(engine)
        startup, _, _ = await edited_narrative(client, engine, token)

        response = await approve(client, token, startup["id"], 1)

        error = assert_error_envelope(response, 409, "NARRATIVE_VERSION_MISMATCH")
        assert "1" in error["detail"] and "2" in error["detail"]
        assert await approval_rows(engine, startup["id"]) == []
        assert (await startup_row(engine, startup["id"]))["status"] != "vc_visible"

    async def test_the_startup_stays_editable_after_a_refused_approval(self, client, engine):
        _, token = await seed_user(engine)
        startup, _, _ = await edited_narrative(client, engine, token)

        await approve(client, token, startup["id"], 1)

        saved = await save_narrative(client, token, startup["id"], FOUNDER_TEXT_2)
        assert saved.status_code == 200, saved.text

    async def test_approving_a_version_that_does_not_exist_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])

        response = await approve(client, token, startup["id"], 99)

        assert_error_envelope(response, 409, "NARRATIVE_VERSION_MISMATCH")
        assert await approval_rows(engine, startup["id"]) == []

    async def test_the_error_detail_carries_version_numbers_but_no_narrative_text(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup, _, _ = await edited_narrative(client, engine, token)

        response = await approve(client, token, startup["id"], 1)

        for fragment in ("Biz kimmiz", "raqamlashtiramiz", "Draft narrative"):
            assert fragment not in response.text


class TestPreconditions:
    async def test_approving_before_any_report_is_a_clean_conflict(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await approve(client, token, startup["id"], 1)

        assert_error_envelope(response, 409, "NARRATIVE_NOT_READY")
        assert await approval_rows(engine, startup["id"]) == []
        assert (await startup_row(engine, startup["id"]))["status"] != "vc_visible"

    async def test_approving_a_never_materialized_narrative_is_refused_and_seeds_nothing(
        self, client, engine
    ):
        # Approval must never be the thing that creates the narrative: a
        # founder cannot freeze text they have not read.
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        response = await approve(client, token, startup["id"], 1)

        assert_error_envelope(response, 409, "NARRATIVE_NOT_READY")
        assert await version_rows(engine, startup["id"]) == []
        assert await approval_rows(engine, startup["id"]) == []

    async def test_a_startup_locked_without_an_approval_cannot_be_approved(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])
        await run_sql(
            engine, "UPDATE startups SET vc_visible_at = now() WHERE id = :id", id=startup["id"]
        )

        response = await approve(client, token, startup["id"], 1)

        assert_error_envelope(response, 409, "STARTUP_LOCKED")
        assert await approval_rows(engine, startup["id"]) == []


class TestFrozenAfterApproval:
    @pytest.fixture()
    async def approved(self, client, engine):
        _, token = await seed_user(engine)
        startup, report, current = await edited_narrative(client, engine, token)
        response = await approve(client, token, startup["id"], current["version"])
        assert response.status_code == 200, response.text
        return token, startup, report, response.json()

    async def test_approving_a_different_version_afterwards_is_locked(
        self, client, engine, approved
    ):
        token, startup, _, body = approved

        response = await approve(client, token, startup["id"], 1)

        assert_error_envelope(response, 409, "STARTUP_LOCKED")
        assert (await get_approval(client, token, startup["id"])).json() == body
        assert len(await approval_rows(engine, startup["id"])) == 1

    async def test_saving_the_narrative_afterwards_is_locked(self, client, engine, approved):
        token, startup, _, _ = approved

        response = await save_narrative(client, token, startup["id"], FOUNDER_TEXT_2)

        assert_error_envelope(response, 409, "STARTUP_LOCKED")
        assert [row["version"] for row in await version_rows(engine, startup["id"])] == [1, 2]

    async def test_editing_the_startup_or_its_answers_afterwards_is_locked(
        self, client, engine, approved
    ):
        token, startup, _, _ = approved

        metadata = await client.patch(
            f"{STARTUPS}/{startup['id']}",
            json={"name": "Renamed After Approval"},
            headers=founder_headers(token, origin=ORIGIN),
        )
        answers = await client.patch(
            f"{STARTUPS}/{startup['id']}/submission",
            json={**COMPLETE_ANSWERS, "problem": "Rewritten after approval."},
            headers=founder_headers(token, origin=ORIGIN),
        )

        assert_error_envelope(metadata, 409, "STARTUP_LOCKED")
        assert_error_envelope(answers, 409, "STARTUP_LOCKED")

    async def test_submitting_or_re_analyzing_afterwards_is_locked(self, client, engine, approved):
        token, startup, _, _ = approved

        submitted = await client.post(
            f"{STARTUPS}/{startup['id']}/submit", headers=founder_headers(token, origin=ORIGIN)
        )
        analyzed = await trigger(client, token, startup["id"], origin=ORIGIN)

        assert_error_envelope(submitted, 409, "STARTUP_LOCKED")
        assert_error_envelope(analyzed, 409, "STARTUP_LOCKED")

    async def test_the_approved_version_stays_exactly_retrievable_alongside_history(
        self, client, engine, approved
    ):
        token, startup, report, body = approved

        approval = await get_approval(client, token, startup["id"])
        history = await list_versions(client, token, startup["id"])
        seed = await get_version(client, token, startup["id"], 1)
        frozen = await get_version(client, token, startup["id"], 2)

        assert approval.json() == body
        assert approval.json()["content"] == FOUNDER_TEXT
        # The earlier revision is still there, still itself, and still not
        # what was approved.
        assert [item["version"] for item in history.json()["versions"]] == [1, 2]
        assert seed.json()["content"] == SEED_DRAFT
        assert frozen.json()["content"] == FOUNDER_TEXT
        assert approval.json()["report_id"] == str(report.id)

    async def test_reading_the_narrative_still_works_once_locked(self, client, engine, approved):
        token, startup, _, _ = approved

        response = await get_narrative(client, token, startup["id"])

        assert response.status_code == 200, response.text
        assert response.json()["content"] == FOUNDER_TEXT


class TestGetApproval:
    async def test_reading_before_any_approval_is_a_canonical_404(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])

        response = await get_approval(client, token, startup["id"])

        assert_error_envelope(response, 404, "NARRATIVE_NOT_APPROVED")

    async def test_reading_after_approval_returns_the_frozen_version(self, client, engine):
        founder_id, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])
        posted = (await approve(client, token, startup["id"], 1)).json()

        response = await get_approval(client, token, startup["id"])

        assert response.status_code == 200, response.text
        assert response.json() == posted
        assert response.json()["approved_by"] == str(founder_id)

    async def test_one_startups_approval_is_never_visible_through_another(self, client, engine):
        _, token = await seed_user(engine)
        first, _ = await startup_with_report(client, engine, token, draft="First startup draft.")
        second, _ = await startup_with_report(client, engine, token, draft="Second startup draft.")
        await read_narrative(client, token, first["id"])
        await read_narrative(client, token, second["id"])
        await approve(client, token, first["id"], 1)

        response = await get_approval(client, token, second["id"])

        assert_error_envelope(response, 404, "NARRATIVE_NOT_APPROVED")


class TestOriginPolicy:
    @pytest.mark.parametrize("origin", [None, "http://evil.example", "http://localhost:5174"])
    async def test_approving_demands_an_exact_allowed_origin(self, client, engine, origin):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])

        response = await approve(client, token, startup["id"], 1, origin=origin)

        assert_error_envelope(response, 403, "FORBIDDEN_ORIGIN")
        assert await approval_rows(engine, startup["id"]) == []
        assert (await startup_row(engine, startup["id"]))["status"] != "vc_visible"

    async def test_reading_the_approval_stays_origin_free(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])
        await approve(client, token, startup["id"], 1)

        assert (await get_approval(client, token, startup["id"])).status_code == 200


class TestOwnershipAndRoles:
    async def test_foreign_and_unknown_startups_share_one_404_on_both_routes(self, client, engine):
        _, owner_token = await seed_user(engine)
        _, other_token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, owner_token)
        await read_narrative(client, owner_token, startup["id"])

        for startup_id in (startup["id"], str(uuid.uuid4())):
            for response in (
                await approve(client, other_token, startup_id, 1),
                await get_approval(client, other_token, startup_id),
            ):
                assert_error_envelope(response, 404, "STARTUP_NOT_FOUND")

    async def test_a_foreign_founder_cannot_freeze_someone_elses_narrative(self, client, engine):
        _, owner_token = await seed_user(engine)
        _, other_token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, owner_token)
        await read_narrative(client, owner_token, startup["id"])

        await approve(client, other_token, startup["id"], 1)

        assert await approval_rows(engine, startup["id"]) == []
        assert (await startup_row(engine, startup["id"]))["status"] != "vc_visible"

    async def test_vc_tokens_are_refused_on_both_routes(self, client, engine):
        _, founder_token = await seed_user(engine)
        _, vc_token = await seed_user(engine, role="vc")
        startup, _ = await startup_with_report(client, engine, founder_token)
        await read_narrative(client, founder_token, startup["id"])

        for response in (
            await approve(client, vc_token, startup["id"], 1),
            await get_approval(client, vc_token, startup["id"]),
        ):
            assert_error_envelope(response, 403, "FORBIDDEN_ROLE")
        assert await approval_rows(engine, startup["id"]) == []

    async def test_missing_token_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        response = await client.get(APPROVAL.format(startup["id"]))

        assert_error_envelope(response, 401, "AUTH_TOKEN_INVALID")


class TestRequestValidation:
    async def test_a_missing_version_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])

        response = await client.post(
            APPROVAL.format(startup["id"]),
            json={},
            headers=founder_headers(token, origin=ORIGIN),
        )

        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert await approval_rows(engine, startup["id"]) == []

    @pytest.mark.parametrize("version", [0, -1, "one", 1.5, None])
    async def test_a_malformed_version_is_refused(self, client, engine, version):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])

        response = await approve(client, token, startup["id"], version)

        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert await approval_rows(engine, startup["id"]) == []

    async def test_client_supplied_approval_metadata_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])

        response = await approve(
            client, token, startup["id"], 1, approved_at="2020-01-01T00:00:00Z"
        )

        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert await approval_rows(engine, startup["id"]) == []


class TestAuditTrail:
    async def test_approval_is_audited_once_with_metadata_only(self, client, engine):
        founder_id, token = await seed_user(engine)
        startup, report, current = await edited_narrative(client, engine, token)

        await approve(client, token, startup["id"], current["version"])

        rows = await approval_audit_rows(engine, startup["id"])
        assert len(rows) == 1
        assert rows[0]["actor_id"] == str(founder_id)
        metadata = rows[0]["metadata_text"]
        assert '"version": 2' in metadata
        assert '"source": "founder_edit"' in metadata
        assert '"status": "vc_visible"' in metadata
        assert str(startup["id"]) in metadata
        assert str(report.id) in metadata
        assert "[REDACTED]" not in metadata

    async def test_audit_metadata_never_carries_narrative_or_report_text(self, client, engine):
        _, token = await seed_user(engine)
        startup, _, current = await edited_narrative(client, engine, token)

        await approve(client, token, startup["id"], current["version"])

        for row in await approval_audit_rows(engine, startup["id"]):
            for fragment in (
                "Biz kimmiz",
                "raqamlashtiramiz",
                "Draft narrative",
                "executive summary",
                "example.com",
            ):
                assert fragment not in row["metadata_text"], row["action"]

    async def test_refused_approvals_are_not_audited(self, client, engine):
        _, token = await seed_user(engine)
        startup, _, _ = await edited_narrative(client, engine, token)

        await approve(client, token, startup["id"], 1)
        await approve(client, token, startup["id"], 1, origin="http://evil.example")

        assert await approval_audit_rows(engine, startup["id"]) == []


class TestNoDeliveryYet:
    async def test_approval_assigns_no_recipient_and_sends_nothing(self, client, engine):
        # Approval freezes the narrative and makes the startup VC-visible.
        # Who sees it, and when it is sent, is deliberately future work: the
        # response carries no recipient and the trail records no delivery.
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await read_narrative(client, token, startup["id"])

        body = (await approve(client, token, startup["id"], 1)).json()

        assert set(body) == EXPECTED_RESPONSE_KEYS
        actions = await fetch_all(
            engine,
            "SELECT action FROM audit_log WHERE entity_id = :sid ORDER BY at, id",
            sid=startup["id"],
        )
        assert "startup.narrative_approved" in [row["action"] for row in actions]
        for row in actions:
            for forbidden in ("send", "deliver", "recipient", "invite_vc"):
                assert forbidden not in row["action"], row["action"]
