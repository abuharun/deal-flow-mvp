"""Founder AI-analysis endpoints (/founder/startups/{id}/analysis).

Contracts under test:
- POST validates every prerequisite (submitted, deck present, demo payment
  paid, current AI/privacy consent) using real metadata-only queries (the
  deck's BYTEA content is never selected) before creating anything. A
  missing prerequisite answers the canonical 422 ANALYSIS_PRECONDITION with
  a bounded, deterministic list of reason codes only.
- On success, exactly one queued job is created, tied to the startup's
  CURRENT input_revision, and the startup moves draft-adjacent statuses to
  'analyzing' -- only on the newly-queued path; idempotent repeats change
  nothing and audit nothing extra.
- Repeated/concurrent POSTs for the same startup return the SAME job (202)
  and never create a second row or a second audit entry.
- GET reports safe status metadata plus `stale` = job.input_revision !=
  startup.input_revision; a missing job is the canonical 404
  ANALYSIS_NOT_FOUND.
- Once VC-visible, POST answers 409 STARTUP_LOCKED; GET stays available.
- Foreign/unknown startups share one 404 STARTUP_NOT_FOUND; VC tokens get
  403 FORBIDDEN_ROLE; POST demands an exact allowed Origin.
- Audit rows carry only startup_id/job_id/input_revision/status -- never
  founder answers, URLs, or PDF data.
- This suite never calls OpenAI and never selects pitch_decks.content.
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from app.db import build_engine, build_sessionmaker
from app.models.consent import CURRENT_AI_PRIVACY_VERSION
from tests.integration.test_founder_decks import make_pdf, upload
from tests.integration.test_founder_startups import (
    assert_error_envelope,
    build_app,
    create_startup,
    fill_answers,
    founder_headers,
    open_client,
    seed_user,
    submit,
)

ANALYSIS = "/founder/startups/{}/analysis"
CONSENTS = "/founder/startups/{}/consents"
PAYMENT = "/founder/startups/{}/payment"
STARTUPS = "/founder/startups"


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def client(test_database_url, db_at_head):
    async with open_client(test_database_url) as c:
        yield c


async def fetch_all(engine, query: str, **params) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(sa.text(query), params)
        return [dict(row) for row in result.mappings()]


async def run_sql(engine, query: str, **params) -> None:
    async with build_sessionmaker(engine)() as session:
        await session.execute(sa.text(query), params)
        await session.commit()


ORIGIN = "http://localhost:5173"


async def trigger(client, token: str, startup_id: str, *, origin: str | None = ORIGIN):
    return await client.post(
        ANALYSIS.format(startup_id), headers=founder_headers(token, origin=origin)
    )


async def get_analysis(client, token: str, startup_id: str):
    return await client.get(ANALYSIS.format(startup_id), headers=founder_headers(token))


async def grant_consent(client, token: str, startup_id: str):
    response = await client.post(
        CONSENTS.format(startup_id),
        json={"kind": "ai_privacy", "text_version": CURRENT_AI_PRIVACY_VERSION},
        headers=founder_headers(token),
    )
    assert response.status_code in (200, 201), response.text
    return response


async def simulate_payment(client, token: str, startup_id: str, outcome: str = "paid"):
    response = await client.post(
        PAYMENT.format(startup_id),
        json={"simulate_outcome": outcome},
        headers=founder_headers(token),
    )
    assert response.status_code in (200, 201), response.text
    return response


async def satisfy_all_prerequisites(client, token: str, startup_id: str) -> None:
    await fill_answers(client, token, startup_id)
    assert (await submit(client, token, startup_id)).status_code == 200
    assert (await upload(client, token, startup_id, make_pdf())).status_code == 201
    await simulate_payment(client, token, startup_id, "paid")
    await grant_consent(client, token, startup_id)


async def analysis_jobs_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, status, attempts, max_attempts, input_revision FROM analysis_jobs "
        "WHERE startup_id = :sid",
        sid=startup_id,
    )


async def analysis_audit_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT action, metadata::text AS metadata_text FROM audit_log "
        "WHERE entity_id = :sid AND action LIKE 'startup.analysis%' ORDER BY at, id",
        sid=startup_id,
    )


class TestPreconditions:
    async def test_missing_everything_reports_all_reasons_in_deterministic_order(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        error = assert_error_envelope(response, 422, "ANALYSIS_PRECONDITION")
        assert error["detail"] == (
            "missing prerequisites: startup_not_submitted, deck_missing, "
            "payment_not_paid, consent_missing"
        )
        assert await analysis_jobs_rows(engine, startup["id"]) == []

    async def test_draft_startup_is_refused_even_with_other_prerequisites_met(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await fill_answers(client, token, startup["id"])
        assert (await upload(client, token, startup["id"], make_pdf())).status_code == 201
        await simulate_payment(client, token, startup["id"])
        await grant_consent(client, token, startup["id"])

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        error = assert_error_envelope(response, 422, "ANALYSIS_PRECONDITION")
        assert "startup_not_submitted" in error["detail"]
        assert await analysis_jobs_rows(engine, startup["id"]) == []

    async def test_missing_deck_is_reported_alone(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await fill_answers(client, token, startup["id"])
        assert (await submit(client, token, startup["id"])).status_code == 200
        await simulate_payment(client, token, startup["id"])
        await grant_consent(client, token, startup["id"])

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        error = assert_error_envelope(response, 422, "ANALYSIS_PRECONDITION")
        assert error["detail"] == "missing prerequisites: deck_missing"

    async def test_unpaid_payment_is_reported_alone(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await fill_answers(client, token, startup["id"])
        assert (await submit(client, token, startup["id"])).status_code == 200
        assert (await upload(client, token, startup["id"], make_pdf())).status_code == 201
        await grant_consent(client, token, startup["id"])

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        error = assert_error_envelope(response, 422, "ANALYSIS_PRECONDITION")
        assert error["detail"] == "missing prerequisites: payment_not_paid"

    async def test_failed_payment_is_reported_as_not_paid(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await fill_answers(client, token, startup["id"])
        assert (await submit(client, token, startup["id"])).status_code == 200
        assert (await upload(client, token, startup["id"], make_pdf())).status_code == 201
        await simulate_payment(client, token, startup["id"], "failed")
        await grant_consent(client, token, startup["id"])

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        error = assert_error_envelope(response, 422, "ANALYSIS_PRECONDITION")
        assert error["detail"] == "missing prerequisites: payment_not_paid"

    async def test_missing_consent_is_reported_alone(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await fill_answers(client, token, startup["id"])
        assert (await submit(client, token, startup["id"])).status_code == 200
        assert (await upload(client, token, startup["id"], make_pdf())).status_code == 201
        await simulate_payment(client, token, startup["id"])

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        error = assert_error_envelope(response, 422, "ANALYSIS_PRECONDITION")
        assert error["detail"] == "missing prerequisites: consent_missing"

    async def test_precondition_failure_never_reveals_another_startups_state(self, client, engine):
        _, token = await seed_user(engine)
        first = await create_startup(client, token)
        second = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, first["id"])

        response = await trigger(client, token, second["id"], origin="http://localhost:5173")

        error = assert_error_envelope(response, 422, "ANALYSIS_PRECONDITION")
        assert first["id"] not in error["detail"]
        assert first["name"] not in error["detail"]


class TestSuccessfulTrigger:
    async def test_trigger_creates_one_queued_job_at_the_current_input_revision(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        before = await client.get(f"{STARTUPS}/{startup['id']}", headers=founder_headers(token))
        input_revision = before.json()["input_revision"]

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        assert response.status_code == 202, response.text
        body = response.json()
        assert uuid.UUID(body["id"])
        assert body["startup_id"] == startup["id"]
        assert body["status"] == "queued"
        assert body["attempts"] == 0
        assert body["max_attempts"] == 3
        assert body["input_revision"] == input_revision
        assert body["stale"] is False
        assert body["started_at"] is None
        assert body["finished_at"] is None

        rows = await analysis_jobs_rows(engine, startup["id"])
        assert len(rows) == 1
        assert rows[0]["status"] == "queued"
        assert rows[0]["input_revision"] == input_revision

    async def test_trigger_moves_the_startup_to_analyzing_without_bumping_input_revision(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        before = await client.get(f"{STARTUPS}/{startup['id']}", headers=founder_headers(token))
        input_revision = before.json()["input_revision"]

        assert (
            await trigger(client, token, startup["id"], origin="http://localhost:5173")
        ).status_code == 202

        after = await client.get(f"{STARTUPS}/{startup['id']}", headers=founder_headers(token))
        assert after.json()["status"] == "analyzing"
        assert after.json()["input_revision"] == input_revision

    async def test_response_never_exposes_answers_urls_or_provider_fields(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        body = response.json()
        for forbidden in (
            "input_tokens",
            "output_tokens",
            "cost_estimate_usd",
            "model",
            "prompt_version",
            "problem",
            "product",
            "dataroom_url",
        ):
            assert forbidden not in body, forbidden

    async def test_trigger_is_audited_with_safe_metadata_only(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")
        job_id = response.json()["id"]

        rows = await analysis_audit_rows(engine, startup["id"])
        assert [row["action"] for row in rows] == ["startup.analysis_trigger"]
        metadata_text = rows[0]["metadata_text"]
        assert startup["id"] in metadata_text
        assert job_id in metadata_text
        assert '"status": "queued"' in metadata_text
        for forbidden in ("problem", "product", "dataroom_url", "%PDF", "prompt_version"):
            assert forbidden not in metadata_text


class TestIdempotentTrigger:
    async def test_second_trigger_returns_the_same_job_unchanged(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])

        first = await trigger(client, token, startup["id"], origin="http://localhost:5173")
        second = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json() == second.json()
        assert len(await analysis_jobs_rows(engine, startup["id"])) == 1

    async def test_idempotent_repeat_does_not_duplicate_the_audit_row(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])

        await trigger(client, token, startup["id"], origin="http://localhost:5173")
        await trigger(client, token, startup["id"], origin="http://localhost:5173")

        assert len(await analysis_audit_rows(engine, startup["id"])) == 1

    async def test_idempotent_repeat_after_completion_still_returns_the_same_job(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        created = (
            await trigger(client, token, startup["id"], origin="http://localhost:5173")
        ).json()
        await run_sql(
            engine,
            "UPDATE analysis_jobs SET status = 'completed', started_at = now(), "
            "finished_at = now() WHERE id = :id",
            id=created["id"],
        )

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        assert response.status_code == 202
        assert response.json()["id"] == created["id"]
        assert response.json()["status"] == "completed"
        assert len(await analysis_jobs_rows(engine, startup["id"])) == 1

    async def test_concurrent_duplicate_triggers_create_one_job_and_one_audit_row(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])

        responses = await asyncio.gather(
            *(
                trigger(client, token, startup["id"], origin="http://localhost:5173")
                for _ in range(5)
            )
        )

        assert all(r.status_code == 202 for r in responses), [r.text for r in responses]
        job_ids = {r.json()["id"] for r in responses}
        assert len(job_ids) == 1
        rows = await analysis_jobs_rows(engine, startup["id"])
        assert len(rows) == 1
        assert len(await analysis_audit_rows(engine, startup["id"])) == 1


class TestGetAnalysisStatus:
    async def test_missing_job_is_a_canonical_404(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await get_analysis(client, token, startup["id"])

        assert_error_envelope(response, 404, "ANALYSIS_NOT_FOUND")

    async def test_get_reports_current_job_status_and_is_not_stale(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        created = (
            await trigger(client, token, startup["id"], origin="http://localhost:5173")
        ).json()

        response = await get_analysis(client, token, startup["id"])

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == created["id"]
        assert body["status"] == "queued"
        assert body["stale"] is False

    async def test_stale_becomes_true_after_a_material_startup_edit(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        await trigger(client, token, startup["id"], origin="http://localhost:5173")

        await client.patch(
            f"{STARTUPS}/{startup['id']}",
            json={"name": "Renamed After Trigger"},
            headers=founder_headers(token, origin="http://localhost:5173"),
        )

        response = await get_analysis(client, token, startup["id"])
        assert response.json()["stale"] is True

    async def test_stale_becomes_true_after_a_deck_replacement(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        await trigger(client, token, startup["id"], origin="http://localhost:5173")

        assert (await upload(client, token, startup["id"], make_pdf(pages=2))).status_code == 200

        response = await get_analysis(client, token, startup["id"])
        assert response.json()["stale"] is True

    async def test_get_never_exposes_unsafe_fields(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        await trigger(client, token, startup["id"], origin="http://localhost:5173")

        response = await get_analysis(client, token, startup["id"])

        body = response.json()
        for forbidden in ("input_tokens", "output_tokens", "cost_estimate_usd", "model"):
            assert forbidden not in body


class TestEligibleStartupStatuses:
    async def test_report_ready_startup_can_still_trigger_a_fresh_job(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        await run_sql(
            engine,
            "UPDATE startups SET status = 'report_ready' WHERE id = :id",
            id=startup["id"],
        )

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        assert response.status_code == 202, response.text


class TestMultiStartupIsolation:
    async def test_analysis_jobs_are_isolated_per_startup(self, client, engine):
        _, token = await seed_user(engine)
        first = await create_startup(client, token)
        second = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, first["id"])

        first_trigger = await trigger(client, token, first["id"], origin="http://localhost:5173")
        second_get = await get_analysis(client, token, second["id"])

        assert first_trigger.status_code == 202
        assert_error_envelope(second_get, 404, "ANALYSIS_NOT_FOUND")


class TestLockedStartups:
    async def test_trigger_on_a_locked_startup_answers_409_even_with_prerequisites_met(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        await run_sql(
            engine, "UPDATE startups SET vc_visible_at = now() WHERE id = :id", id=startup["id"]
        )

        response = await trigger(client, token, startup["id"], origin="http://localhost:5173")

        assert_error_envelope(response, 409, "STARTUP_LOCKED")
        assert await analysis_jobs_rows(engine, startup["id"]) == []

    async def test_get_stays_available_once_a_job_exists_and_the_startup_locks(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        await trigger(client, token, startup["id"], origin="http://localhost:5173")
        await run_sql(
            engine, "UPDATE startups SET vc_visible_at = now() WHERE id = :id", id=startup["id"]
        )

        response = await get_analysis(client, token, startup["id"])

        assert response.status_code == 200


class TestOwnershipAndRoles:
    async def test_foreign_and_unknown_startups_share_one_404(self, client, engine):
        _, owner_token = await seed_user(engine)
        _, other_token = await seed_user(engine)
        startup = await create_startup(client, owner_token)

        for startup_id in (startup["id"], str(uuid.uuid4())):
            post_response = await trigger(
                client, other_token, startup_id, origin="http://localhost:5173"
            )
            assert_error_envelope(post_response, 404, "STARTUP_NOT_FOUND")
            get_response = await get_analysis(client, other_token, startup_id)
            assert_error_envelope(get_response, 404, "STARTUP_NOT_FOUND")

    async def test_vc_tokens_are_refused_on_every_route(self, client, engine):
        _, founder_token = await seed_user(engine)
        _, vc_token = await seed_user(engine, role="vc")
        startup = await create_startup(client, founder_token)

        post_response = await trigger(
            client, vc_token, startup["id"], origin="http://localhost:5173"
        )
        get_response = await get_analysis(client, vc_token, startup["id"])
        assert_error_envelope(post_response, 403, "FORBIDDEN_ROLE")
        assert_error_envelope(get_response, 403, "FORBIDDEN_ROLE")

    async def test_missing_token_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await client.get(ANALYSIS.format(startup["id"]))
        assert_error_envelope(response, 401, "AUTH_TOKEN_INVALID")


class TestOriginPolicy:
    @pytest.mark.parametrize("origin", [None, "https://evil.example"])
    async def test_post_demands_an_exact_allowed_origin(self, client, engine, origin):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])

        response = await trigger(client, token, startup["id"], origin=origin)

        assert_error_envelope(response, 403, "FORBIDDEN_ORIGIN")
        assert await analysis_jobs_rows(engine, startup["id"]) == []

    async def test_reads_stay_origin_free(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        await trigger(client, token, startup["id"], origin="http://localhost:5173")

        response = await client.get(
            ANALYSIS.format(startup["id"]), headers=founder_headers(token, origin=None)
        )
        assert response.status_code == 200


class TestNeverLoadsDeckBytes:
    async def test_trigger_precondition_check_never_selects_deck_content(
        self, test_database_url, db_at_head, engine
    ):
        app = build_app(test_database_url)
        async with app.router.lifespan_context(app):
            import httpx

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                _, token = await seed_user(engine)
                startup = await create_startup(client, token)
                await satisfy_all_prerequisites(client, token, startup["id"])

                statements: list[str] = []
                app_engine = app.state.engine

                @event.listens_for(app_engine.sync_engine, "before_cursor_execute")
                def capture(conn, cursor, statement, parameters, context, executemany):
                    statements.append(statement)

                try:
                    response = await trigger(
                        client, token, startup["id"], origin="http://localhost:5173"
                    )
                    assert response.status_code == 202
                finally:
                    event.remove(app_engine.sync_engine, "before_cursor_execute", capture)

        assert statements, "expected captured SQL for the trigger"
        for statement in statements:
            if "pitch_decks" in statement:
                assert "content" not in statement.lower(), statement
