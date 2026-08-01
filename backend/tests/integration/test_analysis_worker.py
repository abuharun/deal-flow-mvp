"""Claim/execute lifecycle against real Postgres, with a fake OpenAI client.

Covers: no-job-due, the full success path (atomic report + job completion),
snapshot-precondition failures (never call the provider), retryable vs
non-retryable provider failures, attempts exhaustion, stale-input-revision
discard mid-flight, stale-RUNNING-job recovery, and the poll loop's control
flow (no real sleep/network anywhere in this file).
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa

import app.services.analysis_worker as analysis_worker_module
from app.db import build_engine, build_sessionmaker
from app.models.consent import CONSENT_KIND_AI_PRIVACY, CURRENT_AI_PRIVACY_VERSION
from app.models.payment import PAYMENT_STATUS_PAID
from app.repositories.deck_repository import PostgresDeckStorage
from app.services.analysis_worker import (
    JobOutcome,
    recover_stale_running_jobs,
    run_one_job,
    run_worker_loop,
)
from app.services.analysis_worker_config import WorkerConfig
from app.services.openai_provider import ProviderError
from app.services.pdf_validation import validate_deck

VALID_REPORT_PAYLOAD = {
    "schema_version": "report.v1",
    "language": "en",
    "report": {
        "executive_summary": "A concise, non-obvious executive summary.",
        "sections": {
            "uzbekistan_central_asia_market": {"narrative": "Market.", "citation_ids": [1]},
            "global_competitors": {"narrative": "Competitors.", "citation_ids": [2]},
            "us_vc_readiness": {"narrative": "Readiness.", "citation_ids": [3]},
        },
        "competitors": [],
        "claims": [],
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
        "pitch_narrative_draft": "Draft narrative.",
    },
    "sources": [
        {
            "url": f"https://example.com/article-{i}",
            "title": f"Article {i}",
            "accessed_date": "2026-01-01",
            "source_quality": "reputable_media",
            "confidence": "medium",
        }
        for i in (1, 2, 3)
    ],
}


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_analysis_jobs(engine):
    async with build_sessionmaker(engine)() as session:
        await session.execute(sa.text("DELETE FROM analysis_jobs"))
        await session.commit()


def make_config(**overrides) -> WorkerConfig:
    values = dict(
        api_key="sk-test",
        model="gpt-4o-mini",
        prompt_version="analysis.v1",
        report_schema_version="report.v1",
        request_timeout_seconds=30.0,
        max_output_tokens=4000,
        input_price_per_million_usd=Decimal("1.00"),
        output_price_per_million_usd=Decimal("1.00"),
        web_search_cost_usd=Decimal("0.00"),
        max_cost_usd=Decimal("0.25"),
    )
    values.update(overrides)
    return WorkerConfig(**values)


class FakeUsage:
    def __init__(self, input_tokens=1000, output_tokens=1000):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class FakeResponse:
    def __init__(self, payload, input_tokens=1000, output_tokens=1000):
        self.output_text = json.dumps(payload)
        self.usage = FakeUsage(input_tokens, output_tokens)
        self.id = "resp_fake"


class FakeResponses:
    def __init__(self, *, response=None, error=None, on_call=None):
        self._response = response
        self._error = error
        self._on_call = on_call
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self._on_call is not None:
            await self._on_call()
        if self._error is not None:
            raise self._error
        return self._response


class FakeClient:
    def __init__(self, responses: FakeResponses):
        self.responses = responses


def make_pdf_with_text(text: str = "Deck body text.") -> bytes:
    content = f"BT /F1 24 Tf 100 700 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref_offset}\n%%EOF".encode()
    return bytes(out)


async def _insert_founder_with_startup(engine, **startup_overrides) -> tuple[uuid.UUID, uuid.UUID]:
    email = f"worker-{uuid.uuid4().hex}@example.com"
    values = {"status": "submitted", "input_revision": 1}
    values.update(startup_overrides)
    async with build_sessionmaker(engine)() as session:
        founder_id = (
            await session.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role, "
                    "email_verified_at) VALUES (:email, 'x', 'Worker Owner', 'founder', now()) "
                    "RETURNING id"
                ),
                {"email": email},
            )
        ).scalar_one()
        columns = ", ".join(["founder_id", "name", *values.keys()])
        placeholders = ", ".join([":fid", "'Worker Startup'", *(f":{k}" for k in values)])
        startup_id = (
            await session.execute(
                sa.text(f"INSERT INTO startups ({columns}) VALUES ({placeholders}) RETURNING id"),
                {"fid": str(founder_id), **values},
            )
        ).scalar_one()
        await session.execute(
            sa.text(
                "INSERT INTO submissions (startup_id, problem, product, market, traction, "
                "team, ask) VALUES (:sid, 'p', 'p', 'm', 't', 't', 'a')"
            ),
            {"sid": str(startup_id)},
        )
        await session.commit()
    return startup_id, founder_id


async def _grant_consent(engine, startup_id, founder_id) -> None:
    async with build_sessionmaker(engine)() as session:
        await session.execute(
            sa.text(
                "INSERT INTO consents (startup_id, founder_id, kind, text_version) "
                "VALUES (:sid, :fid, :kind, :ver)"
            ),
            {
                "sid": str(startup_id),
                "fid": str(founder_id),
                "kind": CONSENT_KIND_AI_PRIVACY,
                "ver": CURRENT_AI_PRIVACY_VERSION,
            },
        )
        await session.commit()


async def _insert_payment(engine, startup_id) -> None:
    async with build_sessionmaker(engine)() as session:
        await session.execute(
            sa.text(
                "INSERT INTO payments (startup_id, status, paid_at) VALUES (:sid, :status, now())"
            ),
            {"sid": str(startup_id), "status": PAYMENT_STATUS_PAID},
        )
        await session.commit()


async def _put_deck(engine, startup_id, content: bytes | None = None) -> None:
    content = content or make_pdf_with_text()
    deck_file = validate_deck(content, filename="deck.pdf", declared_mime="application/pdf")
    async with build_sessionmaker(engine)() as session:
        await PostgresDeckStorage(session).put(startup_id, deck_file, content)
        await session.commit()


async def _insert_ready_job(engine, **overrides) -> tuple[uuid.UUID, uuid.UUID]:
    startup_id, founder_id = await _insert_founder_with_startup(engine)
    await _grant_consent(engine, startup_id, founder_id)
    await _insert_payment(engine, startup_id)
    await _put_deck(engine, startup_id)
    values = {"startup_id": str(startup_id), "input_revision": 1}
    values.update(overrides)
    async with build_sessionmaker(engine)() as session:
        job_id = (
            await session.execute(
                sa.text(
                    "INSERT INTO analysis_jobs (startup_id, input_revision) "
                    "VALUES (:sid, :rev) RETURNING id"
                ),
                {"sid": str(startup_id), "rev": values["input_revision"]},
            )
        ).scalar_one()
        await session.commit()
    return job_id, startup_id


async def _job_row(engine, job_id) -> dict:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT status, attempts, last_error_code, next_attempt_at, "
                "heartbeat_at, deadline_at, started_at FROM analysis_jobs WHERE id = :id"
            ),
            {"id": job_id},
        )
        return dict(result.mappings().one())


async def _report_count(engine, startup_id) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text("SELECT count(*) FROM analysis_reports WHERE startup_id = :sid"),
            {"sid": startup_id},
        )
        return result.scalar_one()


class TestNoJobDue:
    async def test_returns_no_job_due_and_never_calls_provider(self, engine):
        responses = FakeResponses(response=FakeResponse(VALID_REPORT_PAYLOAD))
        client = FakeClient(responses)
        result = await run_one_job(build_sessionmaker(engine), client=client, config=make_config())
        assert result.outcome is JobOutcome.NO_JOB_DUE
        assert responses.calls == 0


class TestSuccessPath:
    async def test_completes_report_and_job_atomically(self, engine):
        job_id, startup_id = await _insert_ready_job(engine)
        responses = FakeResponses(response=FakeResponse(VALID_REPORT_PAYLOAD))
        client = FakeClient(responses)
        result = await run_one_job(build_sessionmaker(engine), client=client, config=make_config())
        assert result.outcome is JobOutcome.SUCCEEDED
        assert responses.calls == 1
        row = await _job_row(engine, job_id)
        assert row["status"] == "completed"
        assert await _report_count(engine, startup_id) == 1


class TestSnapshotPreconditionFailure:
    async def test_missing_consent_fails_job_without_calling_provider(self, engine):
        startup_id, founder_id = await _insert_founder_with_startup(engine)
        await _insert_payment(engine, startup_id)
        await _put_deck(engine, startup_id)
        async with build_sessionmaker(engine)() as session:
            job_id = (
                await session.execute(
                    sa.text(
                        "INSERT INTO analysis_jobs (startup_id, input_revision) "
                        "VALUES (:sid, 1) RETURNING id"
                    ),
                    {"sid": str(startup_id)},
                )
            ).scalar_one()
            await session.commit()

        responses = FakeResponses(response=FakeResponse(VALID_REPORT_PAYLOAD))
        client = FakeClient(responses)
        result = await run_one_job(build_sessionmaker(engine), client=client, config=make_config())
        assert result.outcome is JobOutcome.FAILED
        assert result.error_code == "SNAPSHOT_CONSENT_MISSING"
        assert responses.calls == 0
        row = await _job_row(engine, job_id)
        assert row["status"] == "failed"
        assert await _report_count(engine, startup_id) == 0


class TestRetryableProviderFailure:
    async def test_retryable_error_marks_retrying_with_backoff(self, engine):
        job_id, _ = await _insert_ready_job(engine)
        error = ProviderError("rate_limited", retryable=True)
        client = FakeClient(FakeResponses(error=error))
        result = await run_one_job(build_sessionmaker(engine), client=client, config=make_config())
        assert result.outcome is JobOutcome.RETRYING
        assert result.error_code == "PROVIDER_RATE_LIMITED"
        row = await _job_row(engine, job_id)
        assert row["status"] == "retrying"
        assert row["attempts"] == 1
        assert row["next_attempt_at"] is not None

    async def test_non_retryable_error_fails_immediately(self, engine):
        job_id, _ = await _insert_ready_job(engine)
        error = ProviderError("auth_error", retryable=False)
        client = FakeClient(FakeResponses(error=error))
        result = await run_one_job(build_sessionmaker(engine), client=client, config=make_config())
        assert result.outcome is JobOutcome.FAILED
        assert result.error_code == "PROVIDER_AUTH_ERROR"
        row = await _job_row(engine, job_id)
        assert row["status"] == "failed"
        assert row["attempts"] == 1

    async def test_attempts_exhausted_after_repeated_retryable_failures(self, engine):
        job_id, _ = await _insert_ready_job(engine)
        now = datetime.now(UTC)
        for attempt in range(1, 4):  # DEFAULT_MAX_ATTEMPTS == 3
            client = FakeClient(FakeResponses(error=ProviderError("timeout", retryable=True)))
            result = await run_one_job(
                build_sessionmaker(engine), client=client, config=make_config(), now=now
            )
            if attempt < 3:
                assert result.outcome is JobOutcome.RETRYING
            else:
                assert result.outcome is JobOutcome.FAILED
            now = now + timedelta(seconds=1000)  # always past next_attempt_at
        row = await _job_row(engine, job_id)
        assert row["status"] == "failed"
        assert row["attempts"] == 3


class TestStaleInputRevisionDiscardedMidFlight:
    async def test_founder_edit_during_provider_call_discards_result(self, engine):
        job_id, startup_id = await _insert_ready_job(engine)

        async def bump_revision_mid_call() -> None:
            # Simulates a founder edit landing WHILE the (slow) provider call
            # is in flight -- a separate connection/transaction, exactly like
            # a concurrent HTTP request would use.
            bump_engine = build_engine(engine.url.render_as_string(hide_password=False))
            try:
                async with build_sessionmaker(bump_engine)() as session:
                    await session.execute(
                        sa.text("UPDATE startups SET input_revision = 2 WHERE id = :sid"),
                        {"sid": str(startup_id)},
                    )
                    await session.commit()
            finally:
                await bump_engine.dispose()

        responses = FakeResponses(
            response=FakeResponse(VALID_REPORT_PAYLOAD), on_call=bump_revision_mid_call
        )
        client = FakeClient(responses)
        result = await run_one_job(build_sessionmaker(engine), client=client, config=make_config())
        assert result.outcome is JobOutcome.FAILED
        assert result.error_code == "STALE_RESULT_DISCARDED"
        assert await _report_count(engine, startup_id) == 0
        row = await _job_row(engine, job_id)
        assert row["status"] == "failed"


class TestStaleRunningJobRecovery:
    async def test_recovers_stale_running_job_with_attempts_remaining_to_retrying(self, engine):
        job_id, _ = await _insert_ready_job(engine)
        past_deadline = datetime.now(UTC) - timedelta(minutes=5)
        async with build_sessionmaker(engine)() as session:
            await session.execute(
                sa.text(
                    "UPDATE analysis_jobs SET status = 'running', attempts = 1, "
                    "started_at = now(), deadline_at = :deadline WHERE id = :id"
                ),
                {"id": job_id, "deadline": past_deadline},
            )
            await session.commit()

        recovered = await recover_stale_running_jobs(build_sessionmaker(engine))
        assert recovered == job_id
        row = await _job_row(engine, job_id)
        assert row["status"] == "retrying"

    async def test_recovers_stale_running_job_at_max_attempts_to_failed(self, engine):
        job_id, _ = await _insert_ready_job(engine)
        past_deadline = datetime.now(UTC) - timedelta(minutes=5)
        async with build_sessionmaker(engine)() as session:
            await session.execute(
                sa.text(
                    "UPDATE analysis_jobs SET status = 'running', attempts = 3, "
                    "started_at = now(), deadline_at = :deadline WHERE id = :id"
                ),
                {"id": job_id, "deadline": past_deadline},
            )
            await session.commit()

        recovered = await recover_stale_running_jobs(build_sessionmaker(engine))
        assert recovered == job_id
        row = await _job_row(engine, job_id)
        assert row["status"] == "failed"

    async def test_does_not_recover_a_running_job_still_within_its_deadline(self, engine):
        job_id, _ = await _insert_ready_job(engine)
        async with build_sessionmaker(engine)() as session:
            await session.execute(
                sa.text(
                    "UPDATE analysis_jobs SET status = 'running', attempts = 1, "
                    "started_at = now(), deadline_at = now() + interval '1 hour' WHERE id = :id"
                ),
                {"id": job_id},
            )
            await session.commit()

        recovered = await recover_stale_running_jobs(build_sessionmaker(engine))
        assert recovered is None


class TestWorkerLoopControlFlow:
    async def test_stops_when_should_continue_becomes_false(self, engine):
        client = FakeClient(FakeResponses(response=FakeResponse(VALID_REPORT_PAYLOAD)))
        calls = {"n": 0}

        def should_continue() -> bool:
            calls["n"] += 1
            return calls["n"] <= 3

        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        iterations = await run_worker_loop(
            build_sessionmaker(engine),
            client=client,
            config=make_config(),
            should_continue=should_continue,
            sleep=fake_sleep,
            poll_interval_seconds=7.5,
        )
        assert iterations == 3
        assert sleeps == [7.5, 7.5, 7.5]  # idle every time: no job was ever due

    async def test_never_sleeps_while_jobs_are_due(self, engine):
        await _insert_ready_job(engine)
        client = FakeClient(FakeResponses(response=FakeResponse(VALID_REPORT_PAYLOAD)))

        calls = {"n": 0}

        def should_continue() -> bool:
            calls["n"] += 1
            return calls["n"] <= 1

        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        await run_worker_loop(
            build_sessionmaker(engine),
            client=client,
            config=make_config(),
            should_continue=should_continue,
            sleep=fake_sleep,
            poll_interval_seconds=7.5,
        )
        assert sleeps == []


class TestDeadline:
    async def test_deadline_is_request_timeout_plus_buffer(self, engine):
        job_id, startup_id = await _insert_ready_job(engine)
        captured: dict = {}

        async def peek_deadline() -> None:
            async with engine.connect() as conn:
                row = (
                    (
                        await conn.execute(
                            sa.text("SELECT deadline_at FROM analysis_jobs WHERE id = :id"),
                            {"id": job_id},
                        )
                    )
                    .mappings()
                    .one()
                )
                captured["deadline_at"] = row["deadline_at"]

        responses = FakeResponses(
            response=FakeResponse(VALID_REPORT_PAYLOAD), on_call=peek_deadline
        )
        client = FakeClient(responses)
        now = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        config = make_config(request_timeout_seconds=45.0)
        await run_one_job(build_sessionmaker(engine), client=client, config=config, now=now)

        expected = now + timedelta(seconds=45.0 + analysis_worker_module._DEADLINE_BUFFER_SECONDS)
        assert captured["deadline_at"] == expected


class TestHeartbeat:
    async def test_heartbeat_is_refreshed_while_provider_call_is_in_flight(self, engine):
        job_id, _ = await _insert_ready_job(engine)
        initial_heartbeat: dict = {}

        async def read_initial_then_hold_the_call_open() -> None:
            # Read the heartbeat_at claiming set (start_running stamps it
            # once, synchronously, before the provider call ever starts) --
            # this is the KNOWN baseline value, not a racy first sample.
            async with engine.connect() as conn:
                row = (
                    (
                        await conn.execute(
                            sa.text("SELECT heartbeat_at FROM analysis_jobs WHERE id = :id"),
                            {"id": job_id},
                        )
                    )
                    .mappings()
                    .one()
                )
                initial_heartbeat["value"] = row["heartbeat_at"]
            # Hold the provider call open for many heartbeat intervals, so the
            # outcome never depends on exactly how the scheduler interleaves
            # a couple of closely-timed samples.
            await asyncio.sleep(0.2)

        responses = FakeResponses(
            response=FakeResponse(VALID_REPORT_PAYLOAD),
            on_call=read_initial_then_hold_the_call_open,
        )
        client = FakeClient(responses)
        result = await run_one_job(
            build_sessionmaker(engine),
            client=client,
            config=make_config(),
            heartbeat_interval_seconds=0.02,
        )
        assert result.outcome is JobOutcome.SUCCEEDED
        assert initial_heartbeat["value"] is not None

        # Read the FINAL heartbeat only after run_one_job has fully returned:
        # by then the heartbeat task has been cancelled and awaited (see its
        # `finally` block), so there is no concurrent writer left in flight
        # and this read can never race a pending update.
        async with engine.connect() as conn:
            final_row = (
                (
                    await conn.execute(
                        sa.text("SELECT heartbeat_at FROM analysis_jobs WHERE id = :id"),
                        {"id": job_id},
                    )
                )
                .mappings()
                .one()
            )
        assert final_row["heartbeat_at"] > initial_heartbeat["value"]

    async def test_heartbeat_loop_stops_cleanly_after_the_call_finishes(self, engine):
        # Regression guard: the heartbeat task must be cancelled (not leaked)
        # once run_one_job returns, and cancellation must never surface as an
        # unhandled exception or task-destroyed warning.
        await _insert_ready_job(engine)
        client = FakeClient(FakeResponses(response=FakeResponse(VALID_REPORT_PAYLOAD)))
        await run_one_job(
            build_sessionmaker(engine),
            client=client,
            config=make_config(),
            heartbeat_interval_seconds=0.01,
        )
        await asyncio.sleep(0.05)
        # Identify leaked tasks by the IDENTITY of the running coroutine's code
        # object, not a substring match on repr(task) -- this test's own name
        # ("..._heartbeat_loop_stops...") contains that substring too, which a
        # naive text match would misidentify as the leaked task.
        heartbeat_code = analysis_worker_module._heartbeat_loop.__code__
        leaked = [
            t
            for t in asyncio.all_tasks()
            if getattr(t.get_coro(), "cr_code", None) is heartbeat_code
        ]
        assert leaked == []


class TestUnexpectedFailureIsHandledSafely:
    async def test_missing_startup_is_failed_safely_not_raised(self, engine, monkeypatch):
        job_id, _ = await _insert_ready_job(engine)

        async def fake_get_for_update(session, *, startup_id, with_submission=False):
            return None

        monkeypatch.setattr(
            analysis_worker_module.startup_repository, "get_for_update", fake_get_for_update
        )
        client = FakeClient(FakeResponses(response=FakeResponse(VALID_REPORT_PAYLOAD)))
        result = await run_one_job(build_sessionmaker(engine), client=client, config=make_config())
        assert result.outcome is JobOutcome.FAILED
        assert result.error_code == "STARTUP_MISSING"

    async def test_unexpected_exception_in_finalize_is_caught_and_job_is_not_left_running(
        self, engine, monkeypatch
    ):
        job_id, startup_id = await _insert_ready_job(engine)

        async def boom(*args, **kwargs):
            raise RuntimeError("db exploded unexpectedly with sensitive detail xyz")

        monkeypatch.setattr(analysis_worker_module, "complete_job_with_report", boom)
        client = FakeClient(FakeResponses(response=FakeResponse(VALID_REPORT_PAYLOAD)))
        result = await run_one_job(build_sessionmaker(engine), client=client, config=make_config())

        assert result.outcome is JobOutcome.FAILED
        assert result.error_code == "WORKER_UNEXPECTED_ERROR"
        assert "sensitive detail xyz" not in (result.error_code or "")
        row = await _job_row(engine, job_id)
        assert row["status"] == "failed"  # never left RUNNING after an unexpected bug
