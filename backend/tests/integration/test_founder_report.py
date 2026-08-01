"""Founder-only immutable AI-report read endpoint (/founder/startups/{id}/report).

Contracts under test:
- A startup with no report yet (no job, or a job not yet completed) answers
  the canonical 404 REPORT_NOT_FOUND -- distinct from STARTUP_NOT_FOUND, so
  the two failure modes never collapse into one signal.
- Foreign/unknown startups share one 404 STARTUP_NOT_FOUND; VC tokens get
  403 FORBIDDEN_ROLE; a missing bearer token gets 401.
- A successful read returns the safe report.v1 projection, normalized
  sources in ordinal order, provenance (schema_version/language/model/
  prompt_version/generated_at/input_revision/partial/evidence_count), and
  `stale` = report.input_revision != startup.input_revision, computed at
  read time.
- The read never exposes another startup's report, the underlying analysis
  job's internal bookkeeping (attempts/error codes/timestamps), or any
  forbidden score/decision field -- report.v1 already forbids those, this
  suite proves the read path can't reintroduce them.
- GET never requires an Origin header.
- This suite never calls OpenAI and completes jobs directly through
  app.services.analysis_report_service (the same seam a future worker would
  use) -- there is no public completion endpoint in this slice.
"""

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from app.db import build_engine, build_sessionmaker
from app.models import Startup
from app.repositories import analysis_repository
from app.schemas.report import ReportV1Input
from app.services import analysis_report_service, analysis_state
from tests.integration.test_founder_analysis import satisfy_all_prerequisites, trigger
from tests.integration.test_founder_startups import (
    assert_error_envelope,
    create_startup,
    founder_headers,
    open_client,
    seed_user,
)

REPORT = "/founder/startups/{}/report"
STARTUPS = "/founder/startups"
ORIGIN = "http://localhost:5173"


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def client(test_database_url, db_at_head):
    async with open_client(test_database_url) as c:
        yield c


async def get_report(client, token: str, startup_id: str, *, origin: str | None = None):
    return await client.get(
        REPORT.format(startup_id), headers=founder_headers(token, origin=origin)
    )


def _source(ordinal_hint: int, **overrides) -> dict:
    values = {
        "url": f"https://example.com/article-{ordinal_hint}",
        "title": f"Article {ordinal_hint}",
        "accessed_date": "2026-01-01",
        "source_quality": "reputable_media",
        "confidence": "medium",
    }
    values.update(overrides)
    return values


def _valid_report_input(**overrides) -> ReportV1Input:
    payload = {
        "schema_version": "report.v1",
        "language": "en",
        "report": {
            "executive_summary": "A concise, non-obvious executive summary of the startup.",
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
                {
                    "name": "Acme Corp",
                    "region": "US",
                    "note": "similar product",
                    "citation_ids": [1],
                }
            ],
            "claims": [
                {
                    "statement": "The market is growing quickly.",
                    "support": "cited",
                    "citation_ids": [1],
                    "confidence": "medium",
                }
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
    payload.update(overrides)
    return ReportV1Input.model_validate(payload)


async def _startup_for_update(session, startup_id: str) -> Startup:
    stmt = sa.select(Startup).where(Startup.id == uuid.UUID(startup_id)).with_for_update()
    return (await session.execute(stmt)).scalar_one()


async def mark_running(engine, job_id: str) -> None:
    async with build_sessionmaker(engine)() as session:
        job = await analysis_repository.get_for_update(session, job_id=uuid.UUID(job_id))
        analysis_state.start_running(job)
        await session.flush()
        await session.commit()


async def complete_report(
    engine,
    startup_id: str,
    job_id: str,
    *,
    input_revision: int | None = None,
    report_input: ReportV1Input | None = None,
    model: str = "gpt-test",
    prompt_version: str = "v1",
    generated_at: datetime | None = None,
):
    async with build_sessionmaker(engine)() as session:
        job = await analysis_repository.get_for_update(session, job_id=uuid.UUID(job_id))
        startup = await _startup_for_update(session, startup_id)
        # The job carries whatever input_revision the startup was at when
        # triggered (fill_answers/submit bump it before trigger) -- default
        # to that so this helper stays correct regardless of how many edits
        # satisfy_all_prerequisites made; callers can still force a mismatch.
        report = await analysis_report_service.complete_job_with_report(
            session,
            job=job,
            startup=startup,
            input_revision=input_revision if input_revision is not None else job.input_revision,
            report_input=report_input or _valid_report_input(),
            model=model,
            prompt_version=prompt_version,
            generated_at=generated_at or datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        )
        await session.commit()
        return report


async def setup_completed_report(client, engine, token: str, startup_id: str, **overrides):
    await satisfy_all_prerequisites(client, token, startup_id)
    triggered = await trigger(client, token, startup_id, origin=ORIGIN)
    assert triggered.status_code == 202, triggered.text
    job_id = triggered.json()["id"]
    await mark_running(engine, job_id)
    return await complete_report(engine, startup_id, job_id, **overrides)


class TestReportNotFound:
    async def test_startup_with_no_analysis_job_gets_report_not_found(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await get_report(client, token, startup["id"])

        assert_error_envelope(response, 404, "REPORT_NOT_FOUND")

    async def test_startup_with_a_queued_job_but_no_report_gets_report_not_found(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        triggered = await trigger(client, token, startup["id"], origin=ORIGIN)
        assert triggered.status_code == 202

        response = await get_report(client, token, startup["id"])

        assert_error_envelope(response, 404, "REPORT_NOT_FOUND")

    async def test_startup_with_a_running_job_but_no_report_gets_report_not_found(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await satisfy_all_prerequisites(client, token, startup["id"])
        triggered = await trigger(client, token, startup["id"], origin=ORIGIN)
        await mark_running(engine, triggered.json()["id"])

        response = await get_report(client, token, startup["id"])

        assert_error_envelope(response, 404, "REPORT_NOT_FOUND")


class TestOwnershipAndRoles:
    async def test_foreign_and_unknown_startups_share_one_404(self, client, engine):
        _, owner_token = await seed_user(engine)
        _, other_token = await seed_user(engine)
        startup = await create_startup(client, owner_token)
        await setup_completed_report(client, engine, owner_token, startup["id"])

        for startup_id in (startup["id"], str(uuid.uuid4())):
            response = await get_report(client, other_token, startup_id)
            assert_error_envelope(response, 404, "STARTUP_NOT_FOUND")

    async def test_vc_tokens_are_refused(self, client, engine):
        _, founder_token = await seed_user(engine)
        _, vc_token = await seed_user(engine, role="vc")
        startup = await create_startup(client, founder_token)
        await setup_completed_report(client, engine, founder_token, startup["id"])

        response = await get_report(client, vc_token, startup["id"])

        assert_error_envelope(response, 403, "FORBIDDEN_ROLE")

    async def test_missing_token_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await client.get(REPORT.format(startup["id"]))

        assert_error_envelope(response, 401, "AUTH_TOKEN_INVALID")


class TestMultiStartupIsolation:
    async def test_reports_are_isolated_per_startup(self, client, engine):
        _, token = await seed_user(engine)
        first = await create_startup(client, token)
        second = await create_startup(client, token)
        await setup_completed_report(client, engine, token, first["id"])

        second_response = await get_report(client, token, second["id"])

        assert_error_envelope(second_response, 404, "REPORT_NOT_FOUND")


class TestSuccessfulRead:
    async def test_returns_the_safe_report_projection_sources_and_provenance(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        report = await setup_completed_report(client, engine, token, startup["id"])

        response = await get_report(client, token, startup["id"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["startup_id"] == startup["id"]
        assert body["schema_version"] == "report.v1"
        assert body["language"] == "en"
        assert body["model"] == "gpt-test"
        assert body["prompt_version"] == "v1"
        assert body["partial"] is False
        assert body["evidence_count"] == 3
        assert body["input_revision"] == report.input_revision
        assert body["stale"] is False
        assert body["report"]["executive_summary"]
        assert body["report"]["sections"]["us_vc_readiness"]["citation_ids"] == [3]
        assert [s["ordinal"] for s in body["sources"]] == [1, 2, 3]
        assert body["sources"][0]["url"] == "https://example.com/article-1"
        assert body["sources"][0]["source_quality"] == "reputable_media"

    async def test_never_exposes_analysis_job_bookkeeping_or_forbidden_fields(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await setup_completed_report(client, engine, token, startup["id"])

        response = await get_report(client, token, startup["id"])

        body = response.json()
        for forbidden in (
            "attempts",
            "max_attempts",
            "last_error_code",
            "last_error_message_key",
            "queued_at",
            "started_at",
            "finished_at",
            "next_attempt_at",
            "investment_score",
            "score",
            "rating",
            "recommend",
            "decision",
        ):
            assert forbidden not in body
            assert forbidden not in body["report"]

    async def test_reads_stay_origin_free(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await setup_completed_report(client, engine, token, startup["id"])

        response = await get_report(client, token, startup["id"], origin=None)

        assert response.status_code == 200


class TestStaleFlag:
    async def test_stale_becomes_true_after_a_material_startup_edit(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await setup_completed_report(client, engine, token, startup["id"])

        patched = await client.patch(
            f"{STARTUPS}/{startup['id']}",
            json={"name": "Renamed After Report"},
            headers=founder_headers(token, origin=ORIGIN),
        )
        assert patched.status_code == 200, patched.text

        response = await get_report(client, token, startup["id"])

        assert response.json()["stale"] is True
        # Immutability: the report itself never changed, only staleness.
        assert response.json()["report"]["executive_summary"] == (
            "A concise, non-obvious executive summary of the startup."
        )

    async def test_report_ready_startup_stays_readable_and_fresh_without_edits(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await setup_completed_report(client, engine, token, startup["id"])

        response = await get_report(client, token, startup["id"])

        assert response.status_code == 200
        assert response.json()["stale"] is False
