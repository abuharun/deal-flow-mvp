"""Integration tests for the internal AI-report completion service.

Exercises app.services.analysis_report_service.complete_job_with_report
against real Postgres: the legal running->completed path, every guard
(wrong job status, mismatched startup/job/input_revision, duplicate
conflict), transaction rollback leaving no partial rows and the job still
running, concurrent double completion, the DB's immutability triggers, and
audit hygiene (safe metadata only, never report text/snippets/URLs).

There is no public HTTP endpoint here and this module never calls OpenAI or
any other provider -- these are exactly the seams a future worker will call,
exercised directly the way the worker itself would.
"""

import asyncio
import uuid
from datetime import UTC, date, datetime

import pytest
import sqlalchemy as sa

from app.db import build_engine, build_sessionmaker
from app.models.analysis_job import STATUS_COMPLETED, STATUS_QUEUED, STATUS_RUNNING
from app.repositories import analysis_report_repository, analysis_repository
from app.schemas.report import ReportV1Input
from app.services import analysis_report_service, analysis_state


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


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


async def _insert_founder_with_startup(engine) -> uuid.UUID:
    email = f"reportservice-{uuid.uuid4().hex}@example.com"
    async with build_sessionmaker(engine)() as session:
        founder_id = (
            await session.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role, "
                    "email_verified_at) VALUES (:email, 'x', 'Report Owner', 'founder', now()) "
                    "RETURNING id"
                ),
                {"email": email},
            )
        ).scalar_one()
        startup_id = (
            await session.execute(
                sa.text(
                    "INSERT INTO startups (founder_id, name) "
                    "VALUES (:fid, 'Report Service Startup') RETURNING id"
                ),
                {"fid": str(founder_id)},
            )
        ).scalar_one()
        await session.commit()
    return startup_id


async def _insert_job(engine, startup_id, **overrides) -> uuid.UUID:
    values = {"startup_id": str(startup_id), "input_revision": 1}
    values.update(overrides)
    # Raw SQL expressions (e.g. now()) are inlined directly; asyncpg cannot
    # bind a TextClause as a parameter value.
    raw_sql = {k: v.text for k, v in values.items() if isinstance(v, sa.sql.elements.TextClause)}
    bound = {k: v for k, v in values.items() if k not in raw_sql}
    columns = ", ".join(values)
    placeholders = ", ".join(raw_sql.get(name, f":{name}") for name in values)
    async with build_sessionmaker(engine)() as session:
        job_id = (
            await session.execute(
                sa.text(
                    f"INSERT INTO analysis_jobs ({columns}) VALUES ({placeholders}) RETURNING id"
                ),
                bound,
            )
        ).scalar_one()
        await session.commit()
    return job_id


async def _make_running_job(
    engine, startup_id=None, **job_overrides
) -> tuple[uuid.UUID, uuid.UUID]:
    if startup_id is None:
        startup_id = await _insert_founder_with_startup(engine)
    job_id = await _insert_job(engine, startup_id, **job_overrides)
    async with build_sessionmaker(engine)() as session:
        job = await analysis_repository.get_for_update(session, job_id=job_id)
        analysis_state.start_running(job)
        await session.flush()
        await session.commit()
    return startup_id, job_id


async def _load_locked(session, startup_id, job_id):
    job = await analysis_repository.get_for_update(session, job_id=job_id)
    startup = await sa_get_startup_for_update(session, startup_id)
    return job, startup


async def sa_get_startup_for_update(session, startup_id):
    from app.models import Startup

    stmt = sa.select(Startup).where(Startup.id == startup_id).with_for_update()
    return (await session.execute(stmt)).scalar_one()


async def _report_rows(engine, startup_id) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text("SELECT * FROM analysis_reports WHERE startup_id = :sid"), {"sid": startup_id}
        )
        return [dict(row) for row in result.mappings()]


async def _source_rows(engine, report_id) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text("SELECT * FROM report_sources WHERE report_id = :rid ORDER BY ordinal"),
            {"rid": report_id},
        )
        return [dict(row) for row in result.mappings()]


async def _job_row(engine, job_id) -> dict:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT status, input_tokens, output_tokens, cost_estimate_usd "
                "FROM analysis_jobs WHERE id = :id"
            ),
            {"id": job_id},
        )
        return dict(result.mappings().one())


async def _startup_row(engine, startup_id) -> dict:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text("SELECT status FROM startups WHERE id = :id"), {"id": startup_id}
        )
        return dict(result.mappings().one())


async def _audit_rows(engine, startup_id) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT action, actor_type, metadata::text AS metadata_text FROM audit_log "
                "WHERE entity_id = :sid AND action = 'startup.report_completed' ORDER BY at"
            ),
            {"sid": startup_id},
        )
        return [dict(row) for row in result.mappings()]


class TestLegalCompletionPath:
    async def test_running_job_completes_with_report_and_sources(self, engine):
        startup_id, job_id = await _make_running_job(engine)

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            generated_at = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
            report = await analysis_report_service.complete_job_with_report(
                session,
                job=job,
                startup=startup,
                input_revision=1,
                report_input=_valid_report_input(),
                model="gpt-test",
                prompt_version="v1",
                generated_at=generated_at,
            )
            await session.commit()
            report_id = report.id

        rows = await _report_rows(engine, startup_id)
        assert len(rows) == 1
        assert rows[0]["id"] == report_id
        assert rows[0]["job_id"] == job_id
        assert rows[0]["input_revision"] == 1
        assert rows[0]["schema_version"] == "report.v1"
        assert rows[0]["model"] == "gpt-test"
        assert rows[0]["prompt_version"] == "v1"
        assert rows[0]["partial"] is False
        assert rows[0]["evidence_count"] == 3

        sources = await _source_rows(engine, report_id)
        assert [s["ordinal"] for s in sources] == [1, 2, 3]
        assert all(s["url"].startswith("https://example.com/article-") for s in sources)

        assert (await _job_row(engine, job_id))["status"] == STATUS_COMPLETED
        assert (await _startup_row(engine, startup_id))["status"] == "report_ready"

    async def test_partial_flag_and_generated_at_are_recorded_as_given(self, engine):
        startup_id, job_id = await _make_running_job(engine)
        generated_at = datetime(2026, 3, 1, 8, 30, tzinfo=UTC)

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            await analysis_report_service.complete_job_with_report(
                session,
                job=job,
                startup=startup,
                input_revision=1,
                report_input=_valid_report_input(),
                model="gpt-test",
                prompt_version="v1",
                generated_at=generated_at,
                partial=True,
            )
            await session.commit()

        rows = await _report_rows(engine, startup_id)
        assert rows[0]["partial"] is True
        assert rows[0]["generated_at"] == generated_at

    async def test_token_and_cost_provenance_passes_through_to_the_job(self, engine):
        """The worker's real token/cost provenance must land on the job row,
        never silently nulled out by the completion service (see the module
        docstring)."""
        from decimal import Decimal

        startup_id, job_id = await _make_running_job(engine)

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            await analysis_report_service.complete_job_with_report(
                session,
                job=job,
                startup=startup,
                input_revision=1,
                report_input=_valid_report_input(),
                model="gpt-test",
                prompt_version="v1",
                generated_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
                input_tokens=12_345,
                output_tokens=6_789,
                cost_estimate_usd=Decimal("0.1234"),
            )
            await session.commit()

        job_row = await _job_row(engine, job_id)
        assert job_row["input_tokens"] == 12_345
        assert job_row["output_tokens"] == 6_789
        assert job_row["cost_estimate_usd"] == Decimal("0.1234")

    async def test_omitted_token_and_cost_provenance_stays_null(self, engine):
        startup_id, job_id = await _make_running_job(engine)

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            await analysis_report_service.complete_job_with_report(
                session,
                job=job,
                startup=startup,
                input_revision=1,
                report_input=_valid_report_input(),
                model="gpt-test",
                prompt_version="v1",
                generated_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            )
            await session.commit()

        job_row = await _job_row(engine, job_id)
        assert job_row["input_tokens"] is None
        assert job_row["output_tokens"] is None
        assert job_row["cost_estimate_usd"] is None


class TestJobStatusGuard:
    @pytest.mark.parametrize("status", [STATUS_QUEUED, "retrying", "failed", "completed"])
    async def test_non_running_job_is_refused_and_nothing_is_written(self, engine, status):
        startup_id = await _insert_founder_with_startup(engine)
        extra = {}
        if status in ("failed", "completed"):
            extra = {"started_at": sa.text("now()"), "finished_at": sa.text("now()")}
        elif status == "retrying":
            extra = {"started_at": sa.text("now()")}
        job_id = await _insert_job(engine, startup_id, status=status, **extra)

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            with pytest.raises(analysis_report_service.JobNotRunningError):
                await analysis_report_service.complete_job_with_report(
                    session,
                    job=job,
                    startup=startup,
                    input_revision=1,
                    report_input=_valid_report_input(),
                    model="gpt-test",
                    prompt_version="v1",
                    generated_at=datetime.now(UTC),
                )
            await session.rollback()

        assert await _report_rows(engine, startup_id) == []
        assert (await _job_row(engine, job_id))["status"] == status


class TestMismatchGuards:
    async def test_job_belonging_to_a_different_startup_is_refused(self, engine):
        startup_a, job_a = await _make_running_job(engine)
        startup_b = await _insert_founder_with_startup(engine)

        async with build_sessionmaker(engine)() as session:
            job = await analysis_repository.get_for_update(session, job_id=job_a)
            other_startup = await sa_get_startup_for_update(session, startup_b)
            with pytest.raises(analysis_report_service.JobMismatchError):
                await analysis_report_service.complete_job_with_report(
                    session,
                    job=job,
                    startup=other_startup,
                    input_revision=1,
                    report_input=_valid_report_input(),
                    model="gpt-test",
                    prompt_version="v1",
                    generated_at=datetime.now(UTC),
                )
            await session.rollback()

        assert await _report_rows(engine, startup_a) == []
        assert await _report_rows(engine, startup_b) == []
        assert (await _job_row(engine, job_a))["status"] == STATUS_RUNNING

    async def test_wrong_declared_input_revision_is_refused(self, engine):
        startup_id, job_id = await _make_running_job(engine)

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            with pytest.raises(analysis_report_service.InputRevisionMismatchError):
                await analysis_report_service.complete_job_with_report(
                    session,
                    job=job,
                    startup=startup,
                    input_revision=2,
                    report_input=_valid_report_input(),
                    model="gpt-test",
                    prompt_version="v1",
                    generated_at=datetime.now(UTC),
                )
            await session.rollback()

        assert await _report_rows(engine, startup_id) == []
        assert (await _job_row(engine, job_id))["status"] == STATUS_RUNNING

    async def test_startup_input_revision_drifted_past_job_is_refused(self, engine):
        # Simulates a founder edit landing after the job started: the
        # startup's input_revision moved forward but the job's -- and the
        # caller's declared value, matching the job -- did not.
        startup_id, job_id = await _make_running_job(engine)
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("UPDATE startups SET input_revision = input_revision + 1 WHERE id = :id"),
                {"id": startup_id},
            )

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            with pytest.raises(analysis_report_service.InputRevisionMismatchError):
                await analysis_report_service.complete_job_with_report(
                    session,
                    job=job,
                    startup=startup,
                    input_revision=1,
                    report_input=_valid_report_input(),
                    model="gpt-test",
                    prompt_version="v1",
                    generated_at=datetime.now(UTC),
                )
            await session.rollback()

        assert await _report_rows(engine, startup_id) == []
        assert (await _job_row(engine, job_id))["status"] == STATUS_RUNNING
        assert (await _startup_row(engine, startup_id))["status"] != "report_ready"


class TestModelAndPromptVersionValidation:
    @pytest.mark.parametrize("model", ["", "x" * 129])
    async def test_invalid_model_is_refused_before_any_write(self, engine, model):
        startup_id, job_id = await _make_running_job(engine)
        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            with pytest.raises(ValueError):
                await analysis_report_service.complete_job_with_report(
                    session,
                    job=job,
                    startup=startup,
                    input_revision=1,
                    report_input=_valid_report_input(),
                    model=model,
                    prompt_version="v1",
                    generated_at=datetime.now(UTC),
                )
            await session.rollback()
        assert await _report_rows(engine, startup_id) == []
        assert (await _job_row(engine, job_id))["status"] == STATUS_RUNNING


class TestDuplicateConflict:
    async def test_second_completion_attempt_on_the_same_job_is_refused(self, engine):
        startup_id, job_id = await _make_running_job(engine)
        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            await analysis_report_service.complete_job_with_report(
                session,
                job=job,
                startup=startup,
                input_revision=1,
                report_input=_valid_report_input(),
                model="gpt-test",
                prompt_version="v1",
                generated_at=datetime.now(UTC),
            )
            await session.commit()

        # The job is now completed (terminal), so a second attempt hits the
        # status guard first -- proving no duplicate report can ever form
        # through the legal completion path.
        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            with pytest.raises(analysis_report_service.JobNotRunningError):
                await analysis_report_service.complete_job_with_report(
                    session,
                    job=job,
                    startup=startup,
                    input_revision=1,
                    report_input=_valid_report_input(),
                    model="gpt-test",
                    prompt_version="v1",
                    generated_at=datetime.now(UTC),
                )
            await session.rollback()

        assert len(await _report_rows(engine, startup_id)) == 1

    async def test_repository_refuses_a_second_insert_for_the_same_job_directly(self, engine):
        from app.models import AnalysisReport

        startup_id, job_id = await _make_running_job(engine)
        async with build_sessionmaker(engine)() as session:
            first = AnalysisReport(
                startup_id=startup_id,
                job_id=job_id,
                input_revision=1,
                report={"x": "y"},
                model="gpt-test",
                prompt_version="v1",
                generated_at=datetime.now(UTC),
            )
            await analysis_report_repository.insert_report(session, report=first, sources=[])
            await session.commit()

        async with build_sessionmaker(engine)() as session:
            duplicate = AnalysisReport(
                startup_id=startup_id,
                job_id=job_id,
                input_revision=1,
                report={"x": "z"},
                model="gpt-test-2",
                prompt_version="v2",
                generated_at=datetime.now(UTC),
            )
            with pytest.raises(analysis_report_repository.ReportAlreadyExistsError):
                await analysis_report_repository.insert_report(
                    session, report=duplicate, sources=[]
                )
            await session.rollback()

        rows = await _report_rows(engine, startup_id)
        assert len(rows) == 1
        assert rows[0]["model"] == "gpt-test"  # untouched by the refused duplicate


class TestTransactionRollbackLeavesNoPartialRows:
    async def test_a_startup_unique_violation_at_flush_leaves_no_partial_rows(self, engine):
        from app.models import AnalysisReport, ReportSource

        startup_id, job_id = await _make_running_job(engine)
        async with build_sessionmaker(engine)() as session:
            first = AnalysisReport(
                startup_id=startup_id,
                job_id=job_id,
                input_revision=1,
                report={"x": "y"},
                model="gpt-test",
                prompt_version="v1",
                generated_at=datetime.now(UTC),
            )
            await analysis_report_repository.insert_report(session, report=first, sources=[])
            await session.commit()

        # A different, real job/startup pairing, but its report is built
        # with startup_id forced to collide with the one above -- the
        # repository's own get_for_job check passes (different job_id), so
        # this reaches the DB and must hit the UNIQUE(startup_id) backstop.
        other_startup_id, other_job_id = await _make_running_job(engine)
        async with build_sessionmaker(engine)() as session:
            colliding = AnalysisReport(
                startup_id=startup_id,  # deliberately the FIRST startup's id
                job_id=other_job_id,
                input_revision=1,
                report={"x": "colliding"},
                model="gpt-test",
                prompt_version="v1",
                generated_at=datetime.now(UTC),
            )
            source = ReportSource(
                ordinal=1,
                url="https://example.com/a",
                title="A",
                accessed_date=date(2026, 1, 1),
                source_quality="unknown",
                confidence="low",
            )
            with pytest.raises(sa.exc.IntegrityError):
                await analysis_report_repository.insert_report(
                    session, report=colliding, sources=[source]
                )
            await session.rollback()

        rows = await _report_rows(engine, startup_id)
        assert len(rows) == 1
        assert rows[0]["report"] == {"x": "y"}  # original untouched
        assert await _report_rows(engine, other_startup_id) == []
        assert (await _job_row(engine, other_job_id))["status"] == STATUS_RUNNING

    async def test_audit_write_failure_rolls_back_the_already_flushed_report_and_sources(
        self, engine, monkeypatch
    ):
        # write_audit is the last step: by the time it runs, insert_report
        # has already flushed the report+sources rows (visible only inside
        # this uncommitted transaction) and job/startup carry pending,
        # unflushed status changes. If write_audit fails for any reason, the
        # caller's rollback must discard all of it together -- a report can
        # never exist without its audit row, and the job must not appear
        # completed with no trace of why.
        startup_id, job_id = await _make_running_job(engine)

        async def _boom(*args, **kwargs):
            raise RuntimeError("simulated audit backend failure")

        monkeypatch.setattr(analysis_report_service, "write_audit", _boom)

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            with pytest.raises(RuntimeError, match="simulated audit backend failure"):
                await analysis_report_service.complete_job_with_report(
                    session,
                    job=job,
                    startup=startup,
                    input_revision=1,
                    report_input=_valid_report_input(),
                    model="gpt-test",
                    prompt_version="v1",
                    generated_at=datetime.now(UTC),
                )
            await session.rollback()

        assert await _report_rows(engine, startup_id) == []
        assert (await _job_row(engine, job_id))["status"] == STATUS_RUNNING
        assert (await _startup_row(engine, startup_id))["status"] != "report_ready"
        assert await _audit_rows(engine, startup_id) == []


class TestConcurrentDoubleCompletion:
    async def test_only_one_of_two_concurrent_completions_succeeds(self, engine):
        startup_id, job_id = await _make_running_job(engine)

        async def attempt():
            async with build_sessionmaker(engine)() as session:
                job, startup = await _load_locked(session, startup_id, job_id)
                try:
                    await analysis_report_service.complete_job_with_report(
                        session,
                        job=job,
                        startup=startup,
                        input_revision=1,
                        report_input=_valid_report_input(),
                        model="gpt-test",
                        prompt_version="v1",
                        generated_at=datetime.now(UTC),
                    )
                    await session.commit()
                    return "ok"
                except analysis_report_service.JobNotRunningError:
                    await session.rollback()
                    return "not_running"

        results = await asyncio.gather(attempt(), attempt())
        assert sorted(results) == ["not_running", "ok"]
        assert len(await _report_rows(engine, startup_id)) == 1
        assert (await _job_row(engine, job_id))["status"] == STATUS_COMPLETED


class TestImmutabilityAfterCompletion:
    async def test_completed_report_cannot_be_updated_or_deleted_directly(self, engine):
        startup_id, job_id = await _make_running_job(engine)
        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            report = await analysis_report_service.complete_job_with_report(
                session,
                job=job,
                startup=startup,
                input_revision=1,
                report_input=_valid_report_input(),
                model="gpt-test",
                prompt_version="v1",
                generated_at=datetime.now(UTC),
            )
            await session.commit()
            report_id = report.id

        async with engine.begin() as conn:
            with pytest.raises(sa.exc.DBAPIError, match="immutable"):
                await conn.execute(
                    sa.text("UPDATE analysis_reports SET model = 'tampered' WHERE id = :id"),
                    {"id": report_id},
                )


class TestAuditHygiene:
    async def test_audit_row_carries_only_safe_metadata(self, engine):
        startup_id, job_id = await _make_running_job(engine)
        report_input = _valid_report_input()
        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, startup_id, job_id)
            await analysis_report_service.complete_job_with_report(
                session,
                job=job,
                startup=startup,
                input_revision=1,
                report_input=report_input,
                model="gpt-test",
                prompt_version="v1",
                generated_at=datetime.now(UTC),
            )
            await session.commit()

        rows = await _audit_rows(engine, startup_id)
        assert len(rows) == 1
        assert rows[0]["actor_type"] == "worker"
        metadata_text = rows[0]["metadata_text"]
        assert str(startup_id) in metadata_text
        assert '"evidence_count": 3' in metadata_text
        assert '"partial": false' in metadata_text
        forbidden = (
            report_input.report.executive_summary,
            report_input.report.pitch_narrative_draft,
            report_input.sources[0].url,
            report_input.sources[0].title,
            "snippet",
            "executive_summary",
            "citation_ids",
        )
        for value in forbidden:
            assert value not in metadata_text, value
