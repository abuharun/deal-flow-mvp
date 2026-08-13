"""Founder-editable narrative with immutable version history.

Product contract under test (MVP): a startup has exactly ONE free-text pitch
narrative. The founder writes it in whatever language they choose -- the UI
locale (UZ/RU) never splits or keys the text, and no endpoint here takes a
locale. The narrative starts as a copy of the immutable report's
`pitch_narrative_draft`, materialized on the founder's first read, and every
save that actually changes the text appends a new immutable version carrying
the report and startup input_revision it was written against.

Access model mirrors every other founder-startup route: founder bearer
principal (VC gets the canonical 403), founder-scoped SQL lookups (foreign
== unknown == one canonical 404 STARTUP_NOT_FOUND), an exact allowed Origin
on the mutating route only, and the canonical 409 STARTUP_LOCKED once the
startup is VC-visible.

Also asserted here: history is append-only through the API (an older
version's text never changes after later saves), the version list never
ships full text, and the audit trail records version metadata only -- never
a character of the narrative itself.
"""

import uuid

import pytest

from app.db import build_engine
from app.schemas.report import ReportV1Input
from tests.integration.test_founder_analysis import run_sql, satisfy_all_prerequisites, trigger
from tests.integration.test_founder_report import (
    _valid_report_input,
    mark_running,
    setup_completed_report,
)
from tests.integration.test_founder_startups import (
    assert_error_envelope,
    create_startup,
    fetch_all,
    founder_headers,
    open_client,
    seed_user,
)

NARRATIVE = "/founder/startups/{}/narrative"
VERSIONS = "/founder/startups/{}/narrative/versions"
VERSION = "/founder/startups/{}/narrative/versions/{}"
STARTUPS = "/founder/startups"
ORIGIN = "http://localhost:5173"

SEED_DRAFT = "Draft narrative the founder is expected to rewrite."
FOUNDER_TEXT = "## Biz kimmiz\n\nToshkentda yuk tashishni raqamlashtiramiz."
FOUNDER_TEXT_2 = "## Кто мы\n\nМы цифровизируем грузоперевозки в Ташкенте."


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def client(test_database_url, db_at_head):
    async with open_client(test_database_url) as c:
        yield c


def report_with_draft(draft: str) -> ReportV1Input:
    payload = _valid_report_input().model_dump(mode="json")
    payload["report"]["pitch_narrative_draft"] = draft
    return ReportV1Input.model_validate(payload)


async def get_narrative(client, token: str, startup_id: str, *, origin: str | None = None):
    return await client.get(
        NARRATIVE.format(startup_id), headers=founder_headers(token, origin=origin)
    )


async def save_narrative(
    client, token: str, startup_id: str, content: str, *, origin: str | None = ORIGIN, **extra
):
    return await client.patch(
        NARRATIVE.format(startup_id),
        json={"content": content, **extra},
        headers=founder_headers(token, origin=origin),
    )


async def list_versions(client, token: str, startup_id: str):
    return await client.get(VERSIONS.format(startup_id), headers=founder_headers(token))


async def get_version(client, token: str, startup_id: str, version):
    return await client.get(VERSION.format(startup_id, version), headers=founder_headers(token))


async def startup_with_report(client, engine, token: str, *, draft: str = SEED_DRAFT):
    """A founder startup carrying one completed, immutable report."""
    startup = await create_startup(client, token)
    report = await setup_completed_report(
        client, engine, token, startup["id"], report_input=report_with_draft(draft)
    )
    return startup, report


async def version_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT version, content, source, input_revision, report_id::text AS report_id "
        "FROM narrative_versions WHERE startup_id = :sid ORDER BY version",
        sid=startup_id,
    )


async def narrative_audit_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT action, metadata::text AS metadata_text FROM audit_log "
        "WHERE entity_id = :sid AND action LIKE 'startup.narrative%' ORDER BY at, id",
        sid=startup_id,
    )


class TestSeeding:
    async def test_first_read_seeds_version_1_from_the_report_draft(self, client, engine):
        _, token = await seed_user(engine)
        startup, report = await startup_with_report(client, engine, token)

        response = await get_narrative(client, token, startup["id"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["startup_id"] == startup["id"]
        assert body["version"] == 1
        assert body["content"] == SEED_DRAFT
        assert body["source"] == "report_seed"
        assert body["report_id"] == str(report.id)
        assert body["input_revision"] == report.input_revision

    async def test_reading_twice_seeds_exactly_once(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        first = await get_narrative(client, token, startup["id"])
        second = await get_narrative(client, token, startup["id"])

        assert first.json() == second.json()
        assert [row["version"] for row in await version_rows(engine, startup["id"])] == [1]

    async def test_the_version_list_also_materializes_the_seed(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        response = await list_versions(client, token, startup["id"])

        assert response.status_code == 200, response.text
        assert response.json()["current_version"] == 1
        assert [item["version"] for item in response.json()["versions"]] == [1]

    async def test_seeding_survives_a_material_edit_made_before_the_first_read(
        self, client, engine
    ):
        # The report is now stale, but its draft is still the only sensible
        # starting text -- the seed records the CURRENT input_revision, so the
        # provenance shows what the founder's inputs looked like at that point.
        _, token = await seed_user(engine)
        startup, report = await startup_with_report(client, engine, token)
        patched = await client.patch(
            f"{STARTUPS}/{startup['id']}",
            json={"name": "Renamed Before Reading"},
            headers=founder_headers(token, origin=ORIGIN),
        )
        assert patched.status_code == 200, patched.text

        body = (await get_narrative(client, token, startup["id"])).json()

        assert body["content"] == SEED_DRAFT
        assert body["report_id"] == str(report.id)
        assert body["input_revision"] == report.input_revision + 1

    async def test_a_vc_visible_startup_can_still_materialize_and_read_its_narrative(
        self, client, engine
    ):
        # Locking refuses founder EDITS; it must never make the narrative
        # unreadable, and the seed is a copy of the immutable report, not
        # founder input.
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await run_sql(
            engine,
            "UPDATE startups SET vc_visible_at = now() WHERE id = :id",
            id=startup["id"],
        )

        response = await get_narrative(client, token, startup["id"])

        assert response.status_code == 200, response.text
        assert response.json()["content"] == SEED_DRAFT


class TestNoReportYet:
    async def test_reading_before_any_analysis_is_a_clean_conflict(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await get_narrative(client, token, startup["id"])

        assert_error_envelope(response, 409, "NARRATIVE_NOT_READY")

    async def test_reading_while_the_job_is_still_running_is_a_clean_conflict(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        triggered = await trigger(client, token, startup["id"], origin=ORIGIN)
        await mark_running(engine, triggered.json()["id"])

        response = await get_narrative(client, token, startup["id"])

        assert_error_envelope(response, 409, "NARRATIVE_NOT_READY")

    async def test_saving_before_any_report_is_a_clean_conflict_and_writes_nothing(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await save_narrative(client, token, startup["id"], FOUNDER_TEXT)

        assert_error_envelope(response, 409, "NARRATIVE_NOT_READY")
        assert await version_rows(engine, startup["id"]) == []

    async def test_listing_versions_before_any_report_is_a_clean_conflict(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await list_versions(client, token, startup["id"])

        assert_error_envelope(response, 409, "NARRATIVE_NOT_READY")


class TestSaving:
    async def test_a_save_appends_the_next_version_and_moves_the_current_pointer(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup, report = await startup_with_report(client, engine, token)

        response = await save_narrative(client, token, startup["id"], FOUNDER_TEXT)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["version"] == 2
        assert body["content"] == FOUNDER_TEXT
        assert body["source"] == "founder_edit"
        assert body["report_id"] == str(report.id)
        assert (await get_narrative(client, token, startup["id"])).json() == body

    async def test_versions_increase_monotonically_across_repeated_saves(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        for content in (FOUNDER_TEXT, FOUNDER_TEXT_2, f"{FOUNDER_TEXT_2}\n\nYana bir band."):
            assert (await save_narrative(client, token, startup["id"], content)).status_code == 200

        assert [row["version"] for row in await version_rows(engine, startup["id"])] == [1, 2, 3, 4]

    async def test_history_keeps_the_earlier_text_unchanged(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await save_narrative(client, token, startup["id"], FOUNDER_TEXT)

        await save_narrative(client, token, startup["id"], FOUNDER_TEXT_2)

        rows = await version_rows(engine, startup["id"])
        assert [row["content"] for row in rows] == [SEED_DRAFT, FOUNDER_TEXT, FOUNDER_TEXT_2]
        assert [row["source"] for row in rows] == ["report_seed", "founder_edit", "founder_edit"]

    async def test_saving_identical_text_is_a_no_op(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        first = await save_narrative(client, token, startup["id"], FOUNDER_TEXT)

        again = await save_narrative(client, token, startup["id"], FOUNDER_TEXT)

        assert again.status_code == 200, again.text
        assert again.json()["version"] == first.json()["version"] == 2
        assert [row["version"] for row in await version_rows(engine, startup["id"])] == [1, 2]

    async def test_saving_the_seed_text_verbatim_appends_nothing(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        response = await save_narrative(client, token, startup["id"], SEED_DRAFT)

        assert response.json()["version"] == 1
        assert [row["version"] for row in await version_rows(engine, startup["id"])] == [1]

    async def test_a_save_records_the_startups_input_revision_at_that_moment(self, client, engine):
        _, token = await seed_user(engine)
        startup, report = await startup_with_report(client, engine, token)
        await get_narrative(client, token, startup["id"])
        patched = await client.patch(
            f"{STARTUPS}/{startup['id']}",
            json={"name": "Renamed Mid-Edit"},
            headers=founder_headers(token, origin=ORIGIN),
        )
        assert patched.status_code == 200, patched.text

        body = (await save_narrative(client, token, startup["id"], FOUNDER_TEXT)).json()

        assert body["input_revision"] == report.input_revision + 1
        # The lineage still points at the one immutable report it came from.
        assert body["report_id"] == str(report.id)
        rows = await version_rows(engine, startup["id"])
        assert [row["input_revision"] for row in rows] == [
            report.input_revision,
            report.input_revision + 1,
        ]

    async def test_a_save_on_a_never_read_narrative_still_preserves_the_seed_in_history(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        body = (await save_narrative(client, token, startup["id"], FOUNDER_TEXT)).json()

        assert body["version"] == 2
        rows = await version_rows(engine, startup["id"])
        assert [row["content"] for row in rows] == [SEED_DRAFT, FOUNDER_TEXT]

    async def test_line_endings_are_normalized_before_storage(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        body = (await save_narrative(client, token, startup["id"], "a\r\nb\r\nc")).json()

        assert body["content"] == "a\nb\nc"

    @pytest.mark.parametrize(
        "content", ["", "   ", "x" * 20_001, "before\x0bafter", "before\x07after"]
    )
    async def test_invalid_content_is_refused_without_touching_history(
        self, client, engine, content
    ):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await get_narrative(client, token, startup["id"])

        response = await save_narrative(client, token, startup["id"], content)

        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert [row["version"] for row in await version_rows(engine, startup["id"])] == [1]

    async def test_validation_errors_never_echo_the_submitted_narrative(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        secret = "x" * 20_001

        response = await save_narrative(client, token, startup["id"], secret)

        error = assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert secret not in response.text
        assert "content" in error["detail"]

    async def test_client_supplied_provenance_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        response = await save_narrative(
            client, token, startup["id"], FOUNDER_TEXT, version=99, source="report_seed"
        )

        assert_error_envelope(response, 422, "VALIDATION_FAILED")


class TestLocking:
    async def test_a_vc_visible_startup_refuses_saves(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await get_narrative(client, token, startup["id"])
        await run_sql(
            engine,
            "UPDATE startups SET vc_visible_at = now() WHERE id = :id",
            id=startup["id"],
        )

        response = await save_narrative(client, token, startup["id"], FOUNDER_TEXT)

        assert_error_envelope(response, 409, "STARTUP_LOCKED")
        assert [row["version"] for row in await version_rows(engine, startup["id"])] == [1]

    async def test_a_vc_visible_status_alone_also_locks_saves(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await run_sql(
            engine,
            "UPDATE startups SET status = 'vc_visible' WHERE id = :id",
            id=startup["id"],
        )

        response = await save_narrative(client, token, startup["id"], FOUNDER_TEXT)

        assert_error_envelope(response, 409, "STARTUP_LOCKED")


class TestOriginPolicy:
    @pytest.mark.parametrize("origin", [None, "http://evil.example", "http://localhost:5174"])
    async def test_saving_demands_an_exact_allowed_origin(self, client, engine, origin):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        response = await save_narrative(client, token, startup["id"], FOUNDER_TEXT, origin=origin)

        assert_error_envelope(response, 403, "FORBIDDEN_ORIGIN")
        assert await version_rows(engine, startup["id"]) == []

    async def test_reads_stay_origin_free(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        assert (await get_narrative(client, token, startup["id"])).status_code == 200
        assert (await list_versions(client, token, startup["id"])).status_code == 200
        assert (await get_version(client, token, startup["id"], 1)).status_code == 200


class TestOwnershipAndRoles:
    async def test_foreign_and_unknown_startups_share_one_404_on_every_route(self, client, engine):
        _, owner_token = await seed_user(engine)
        _, other_token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, owner_token)
        await get_narrative(client, owner_token, startup["id"])

        for startup_id in (startup["id"], str(uuid.uuid4())):
            for response in (
                await get_narrative(client, other_token, startup_id),
                await save_narrative(client, other_token, startup_id, FOUNDER_TEXT),
                await list_versions(client, other_token, startup_id),
                await get_version(client, other_token, startup_id, 1),
            ):
                assert_error_envelope(response, 404, "STARTUP_NOT_FOUND")

    async def test_a_foreign_founder_cannot_append_a_version(self, client, engine):
        _, owner_token = await seed_user(engine)
        _, other_token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, owner_token)
        await get_narrative(client, owner_token, startup["id"])

        await save_narrative(client, other_token, startup["id"], FOUNDER_TEXT)

        assert [row["content"] for row in await version_rows(engine, startup["id"])] == [SEED_DRAFT]

    async def test_vc_tokens_are_refused_on_every_route(self, client, engine):
        _, founder_token = await seed_user(engine)
        _, vc_token = await seed_user(engine, role="vc")
        startup, _ = await startup_with_report(client, engine, founder_token)
        await get_narrative(client, founder_token, startup["id"])

        for response in (
            await get_narrative(client, vc_token, startup["id"]),
            await save_narrative(client, vc_token, startup["id"], FOUNDER_TEXT),
            await list_versions(client, vc_token, startup["id"]),
            await get_version(client, vc_token, startup["id"], 1),
        ):
            assert_error_envelope(response, 403, "FORBIDDEN_ROLE")

    async def test_missing_token_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        response = await client.get(NARRATIVE.format(startup["id"]))

        assert_error_envelope(response, 401, "AUTH_TOKEN_INVALID")

    async def test_narratives_are_isolated_per_startup(self, client, engine):
        _, token = await seed_user(engine)
        first, _ = await startup_with_report(client, engine, token, draft="First startup draft.")
        second, _ = await startup_with_report(client, engine, token, draft="Second startup draft.")

        await save_narrative(client, token, first["id"], FOUNDER_TEXT)

        other = (await get_narrative(client, token, second["id"])).json()
        assert other["content"] == "Second startup draft."
        assert other["version"] == 1
        assert other["startup_id"] == second["id"]


class TestVersionHistory:
    async def test_the_list_is_metadata_only_in_ascending_version_order(self, client, engine):
        _, token = await seed_user(engine)
        startup, report = await startup_with_report(client, engine, token)
        await save_narrative(client, token, startup["id"], FOUNDER_TEXT)

        response = await list_versions(client, token, startup["id"])

        body = response.json()
        assert body["current_version"] == 2
        assert [item["version"] for item in body["versions"]] == [1, 2]
        assert [item["source"] for item in body["versions"]] == ["report_seed", "founder_edit"]
        for item in body["versions"]:
            assert "content" not in item, "listing history must never ship every revision's text"
            assert item["report_id"] == str(report.id)
            assert item["created_at"]
        assert body["versions"][1]["content_length"] == len(FOUNDER_TEXT)

    async def test_a_specific_version_returns_its_full_immutable_text(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)
        await save_narrative(client, token, startup["id"], FOUNDER_TEXT)

        first = await get_version(client, token, startup["id"], 1)
        second = await get_version(client, token, startup["id"], 2)

        assert first.status_code == 200, first.text
        assert first.json()["content"] == SEED_DRAFT
        assert first.json()["source"] == "report_seed"
        assert second.json()["content"] == FOUNDER_TEXT
        assert second.json()["source"] == "founder_edit"

    async def test_an_unknown_version_is_a_canonical_404(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        response = await get_version(client, token, startup["id"], 7)

        assert_error_envelope(response, 404, "NARRATIVE_VERSION_NOT_FOUND")

    @pytest.mark.parametrize("version", [0, -1, "abc"])
    async def test_a_malformed_version_is_refused(self, client, engine, version):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        response = await get_version(client, token, startup["id"], version)

        assert_error_envelope(response, 422, "VALIDATION_FAILED")

    async def test_one_startups_version_is_never_reachable_through_another(self, client, engine):
        _, token = await seed_user(engine)
        first, _ = await startup_with_report(client, engine, token, draft="First startup draft.")
        second, _ = await startup_with_report(client, engine, token, draft="Second startup draft.")
        await save_narrative(client, token, first["id"], FOUNDER_TEXT)

        response = await get_version(client, token, second["id"], 2)

        assert_error_envelope(response, 404, "NARRATIVE_VERSION_NOT_FOUND")


class TestAuditTrail:
    async def test_seed_and_edit_are_audited_with_metadata_only(self, client, engine):
        _, token = await seed_user(engine)
        startup, report = await startup_with_report(client, engine, token)
        await get_narrative(client, token, startup["id"])

        await save_narrative(client, token, startup["id"], FOUNDER_TEXT)

        rows = await narrative_audit_rows(engine, startup["id"])
        assert [row["action"] for row in rows] == [
            "startup.narrative_seed",
            "startup.narrative_edit",
        ]
        edit_metadata = rows[1]["metadata_text"]
        assert '"version": 2' in edit_metadata
        assert '"source": "founder_edit"' in edit_metadata
        assert str(report.id) in edit_metadata
        # The length is recorded under a key the shared redaction policy does
        # not mask; a "content"-shaped key would be stored as [REDACTED].
        assert f'"character_count": {len(FOUNDER_TEXT)}' in edit_metadata
        assert "[REDACTED]" not in edit_metadata

    async def test_audit_metadata_never_carries_narrative_text(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        await save_narrative(client, token, startup["id"], FOUNDER_TEXT)

        for row in await narrative_audit_rows(engine, startup["id"]):
            for fragment in ("Biz kimmiz", "raqamlashtiramiz", "Draft narrative"):
                assert fragment not in row["metadata_text"], row["action"]

    async def test_a_no_op_save_is_not_audited_as_an_edit(self, client, engine):
        _, token = await seed_user(engine)
        startup, _ = await startup_with_report(client, engine, token)

        await save_narrative(client, token, startup["id"], SEED_DRAFT)

        assert [row["action"] for row in await narrative_audit_rows(engine, startup["id"])] == [
            "startup.narrative_seed"
        ]
