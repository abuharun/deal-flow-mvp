"""Integration tests for the AI-analysis worker's state-machine helpers.

Exercises the full legal lifecycle against real Postgres: row lock (FOR
UPDATE) via analysis_repository.get_for_update, coherent timestamp/attempt/
deadline updates, terminal immutability, illegal transitions, max-attempts
exhaustion, and schema-level rejection of bad token/cost/error values
before any DB write is attempted. No worker loop and no provider call
exists anywhere here -- these are the seams a future worker will call.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from pydantic import ValidationError

from app.db import build_engine, build_sessionmaker
from app.repositories import analysis_repository
from app.schemas.analysis import AnalysisCompletionInput, AnalysisFailureInput
from app.services import analysis_state


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


async def _insert_founder_with_startup(engine) -> uuid.UUID:
    email = f"analysisstate-{uuid.uuid4().hex}@example.com"
    async with build_sessionmaker(engine)() as session:
        founder_id = (
            await session.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role, "
                    "email_verified_at) VALUES (:email, 'x', 'State Owner', 'founder', now()) "
                    "RETURNING id"
                ),
                {"email": email},
            )
        ).scalar_one()
        startup_id = (
            await session.execute(
                sa.text(
                    "INSERT INTO startups (founder_id, name) "
                    "VALUES (:fid, 'State Startup') RETURNING id"
                ),
                {"fid": str(founder_id)},
            )
        ).scalar_one()
        await session.commit()
    return startup_id


async def _insert_queued_job(engine, startup_id, **overrides) -> uuid.UUID:
    values = {"startup_id": str(startup_id), "input_revision": 1}
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{k}" for k in values)
    async with build_sessionmaker(engine)() as session:
        job_id = (
            await session.execute(
                sa.text(
                    f"INSERT INTO analysis_jobs ({columns}) VALUES ({placeholders}) RETURNING id"
                ),
                values,
            )
        ).scalar_one()
        await session.commit()
    return job_id


async def _fetch_job_row(engine, job_id) -> dict:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT status, attempts, max_attempts, started_at, heartbeat_at, finished_at, "
                "next_attempt_at, deadline_at, model, prompt_version, input_tokens, "
                "output_tokens, cost_estimate_usd, last_error_code, last_error_message_key "
                "FROM analysis_jobs WHERE id = :id"
            ),
            {"id": str(job_id)},
        )
        return dict(result.mappings().one())


async def _transition(engine, job_id, apply):
    async with build_sessionmaker(engine)() as session:
        job = await analysis_repository.get_for_update(session, job_id=job_id)
        apply(job)
        await session.flush()
        await session.commit()


class TestFullLifecycleSuccess:
    async def test_queued_running_completed(self, engine):
        startup_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_queued_job(engine, startup_id)

        await _transition(engine, job_id, lambda job: analysis_state.start_running(job))

        row = await _fetch_job_row(engine, job_id)
        assert row["status"] == "running"
        assert row["attempts"] == 1
        assert row["started_at"] is not None
        assert row["heartbeat_at"] is not None
        assert row["finished_at"] is None

        completion = AnalysisCompletionInput(
            model="gpt-test",
            prompt_version="v1",
            input_tokens=10,
            output_tokens=5,
            cost_estimate_usd=Decimal("0.01"),
        )
        await _transition(
            engine, job_id, lambda job: analysis_state.mark_completed(job, completion=completion)
        )

        row = await _fetch_job_row(engine, job_id)
        assert row["status"] == "completed"
        assert row["finished_at"] is not None
        assert row["model"] == "gpt-test"
        assert row["prompt_version"] == "v1"
        assert row["input_tokens"] == 10
        assert row["output_tokens"] == 5
        assert row["cost_estimate_usd"] == Decimal("0.0100")


class TestRetryThenFail:
    async def test_running_retrying_running_failed(self, engine):
        startup_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_queued_job(engine, startup_id, max_attempts=2)

        await _transition(engine, job_id, lambda job: analysis_state.start_running(job))
        next_attempt_at = datetime.now(UTC) + timedelta(minutes=5)
        await _transition(
            engine,
            job_id,
            lambda job: analysis_state.mark_retrying(
                job,
                next_attempt_at=next_attempt_at,
                error_code="PROVIDER_TIMEOUT",
                error_message_key="errors.analysisProviderTimeout",
            ),
        )

        row = await _fetch_job_row(engine, job_id)
        assert row["status"] == "retrying"
        assert row["next_attempt_at"] is not None
        assert row["last_error_code"] == "PROVIDER_TIMEOUT"
        assert row["last_error_message_key"] == "errors.analysisProviderTimeout"

        await _transition(engine, job_id, lambda job: analysis_state.start_running(job))
        row = await _fetch_job_row(engine, job_id)
        assert row["status"] == "running"
        assert row["attempts"] == 2
        assert row["next_attempt_at"] is None

        await _transition(
            engine,
            job_id,
            lambda job: analysis_state.mark_failed(
                job,
                error_code="PROVIDER_TIMEOUT",
                error_message_key="errors.analysisProviderTimeout",
            ),
        )
        row = await _fetch_job_row(engine, job_id)
        assert row["status"] == "failed"
        assert row["finished_at"] is not None


class TestTerminalImmutability:
    @pytest.mark.parametrize("seed_status", ["completed", "failed"])
    async def test_no_transition_is_legal_from_a_terminal_status(self, engine, seed_status):
        startup_id = await _insert_founder_with_startup(engine)
        async with build_sessionmaker(engine)() as session:
            job_id = (
                await session.execute(
                    sa.text(
                        "INSERT INTO analysis_jobs "
                        "(startup_id, input_revision, status, started_at, finished_at) "
                        "VALUES (:sid, 1, :status, now(), now()) RETURNING id"
                    ),
                    {"sid": str(startup_id), "status": seed_status},
                )
            ).scalar_one()
            await session.commit()

        async with build_sessionmaker(engine)() as session:
            job = await analysis_repository.get_for_update(session, job_id=job_id)
            with pytest.raises(analysis_state.TerminalStateError):
                analysis_state.start_running(job)
            with pytest.raises(analysis_state.TerminalStateError):
                analysis_state.mark_completed(job)
            with pytest.raises(analysis_state.TerminalStateError):
                analysis_state.mark_failed(job, error_code="X", error_message_key="errors.x.y")
            await session.rollback()

        row = await _fetch_job_row(engine, job_id)
        assert row["status"] == seed_status


class TestIllegalTransitions:
    async def test_queued_cannot_jump_straight_to_completed(self, engine):
        startup_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_queued_job(engine, startup_id)

        async with build_sessionmaker(engine)() as session:
            job = await analysis_repository.get_for_update(session, job_id=job_id)
            with pytest.raises(analysis_state.IllegalTransitionError):
                analysis_state.mark_completed(job)
            await session.rollback()

        row = await _fetch_job_row(engine, job_id)
        assert row["status"] == "queued"

    async def test_retrying_cannot_go_directly_to_completed(self, engine):
        startup_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_queued_job(engine, startup_id)
        await _transition(engine, job_id, lambda job: analysis_state.start_running(job))
        await _transition(
            engine,
            job_id,
            lambda job: analysis_state.mark_retrying(
                job,
                next_attempt_at=datetime.now(UTC) + timedelta(minutes=1),
                error_code="X",
                error_message_key="errors.x.y",
            ),
        )

        async with build_sessionmaker(engine)() as session:
            job = await analysis_repository.get_for_update(session, job_id=job_id)
            with pytest.raises(analysis_state.IllegalTransitionError):
                analysis_state.mark_completed(job)
            await session.rollback()


class TestMaxAttemptsExceeded:
    async def test_start_running_refuses_once_attempts_reach_the_cap(self, engine):
        startup_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_queued_job(engine, startup_id, max_attempts=1, attempts=1)

        async with build_sessionmaker(engine)() as session:
            job = await analysis_repository.get_for_update(session, job_id=job_id)
            with pytest.raises(analysis_state.MaxAttemptsExceededError):
                analysis_state.start_running(job)
            await session.rollback()

        row = await _fetch_job_row(engine, job_id)
        assert row["status"] == "queued"
        assert row["attempts"] == 1


class TestRowLockSerializesConcurrentTransitions:
    async def test_concurrent_start_running_only_one_wins(self, engine):
        startup_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_queued_job(engine, startup_id)

        async def attempt():
            try:
                await _transition(engine, job_id, lambda job: analysis_state.start_running(job))
                return "ok"
            except analysis_state.IllegalTransitionError:
                return "illegal"

        results = await asyncio.gather(attempt(), attempt())
        assert sorted(results) == ["illegal", "ok"]

        row = await _fetch_job_row(engine, job_id)
        assert row["status"] == "running"
        assert row["attempts"] == 1


class TestSchemaLevelValidation:
    def test_negative_tokens_are_rejected(self):
        with pytest.raises(ValidationError):
            AnalysisCompletionInput(input_tokens=-1)
        with pytest.raises(ValidationError):
            AnalysisCompletionInput(output_tokens=-1)

    def test_cost_estimate_above_cap_is_rejected(self):
        with pytest.raises(ValidationError):
            AnalysisCompletionInput(cost_estimate_usd=Decimal("0.26"))

    def test_negative_cost_estimate_is_rejected(self):
        with pytest.raises(ValidationError):
            AnalysisCompletionInput(cost_estimate_usd=Decimal("-0.01"))

    def test_cost_estimate_at_the_cap_is_accepted(self):
        completion = AnalysisCompletionInput(cost_estimate_usd=Decimal("0.25"))
        assert completion.cost_estimate_usd == Decimal("0.25")

    @pytest.mark.parametrize("error_code", ["", "lowercase", "HAS SPACE", "HAS-DASH", "x" * 65])
    def test_unsafe_error_codes_are_rejected(self, error_code):
        with pytest.raises(ValidationError):
            AnalysisFailureInput(error_code=error_code, error_message_key="errors.analysisFailed")

    @pytest.mark.parametrize("message_key", ["", "NoDotNamespace", "errors", ".errors.leading"])
    def test_unsafe_error_message_keys_are_rejected(self, message_key):
        with pytest.raises(ValidationError):
            AnalysisFailureInput(error_code="PROVIDER_TIMEOUT", error_message_key=message_key)
