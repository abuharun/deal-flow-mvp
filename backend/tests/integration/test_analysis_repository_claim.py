"""claim_next_due_job: FOR UPDATE SKIP LOCKED, deterministic FIFO, no double-claim."""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from app.db import build_engine, build_sessionmaker
from app.models.analysis_job import STATUS_COMPLETED, STATUS_QUEUED, STATUS_RETRYING, STATUS_RUNNING
from app.repositories.analysis_repository import claim_next_due_job


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_analysis_jobs(engine):
    # This suite asserts on the GLOBAL set of due jobs (claim_next_due_job has
    # no startup filter by design), so -- unlike other integration tests here
    # that only ever assert on their own specific ids -- it needs a clean
    # table rather than tolerating whatever earlier tests left behind.
    async with build_sessionmaker(engine)() as session:
        await session.execute(sa.text("DELETE FROM analysis_jobs"))
        await session.commit()


async def _insert_founder_with_startup(engine) -> uuid.UUID:
    email = f"claim-{uuid.uuid4().hex}@example.com"
    async with build_sessionmaker(engine)() as session:
        founder_id = (
            await session.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role, "
                    "email_verified_at) VALUES (:email, 'x', 'Claim Owner', 'founder', now()) "
                    "RETURNING id"
                ),
                {"email": email},
            )
        ).scalar_one()
        startup_id = (
            await session.execute(
                sa.text(
                    "INSERT INTO startups (founder_id, name) VALUES (:fid, 'Claim Startup') "
                    "RETURNING id"
                ),
                {"fid": str(founder_id)},
            )
        ).scalar_one()
        await session.commit()
    return startup_id


async def _insert_job(engine, startup_id=None, **overrides) -> uuid.UUID:
    if startup_id is None:
        startup_id = await _insert_founder_with_startup(engine)
    values = {"startup_id": str(startup_id), "input_revision": 1, "status": STATUS_QUEUED}
    values.update(overrides)
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
    return job_id, startup_id


class TestClaimsDueJobs:
    async def test_claims_a_queued_job_with_no_next_attempt_at(self, engine):
        job_id, _ = await _insert_job(engine)
        async with build_sessionmaker(engine)() as session:
            claimed = await claim_next_due_job(session, now=datetime.now(UTC))
            await session.commit()
        assert claimed is not None
        assert claimed.id == job_id

    async def test_claims_a_retrying_job_whose_next_attempt_at_has_passed(self, engine):
        past = sa.text("now() - interval '1 minute'")
        job_id, _ = await _insert_job(
            engine,
            status=STATUS_RETRYING,
            attempts=1,
            started_at=sa.text("now()"),
            next_attempt_at=past,
        )
        async with build_sessionmaker(engine)() as session:
            claimed = await claim_next_due_job(session, now=datetime.now(UTC))
            await session.commit()
        assert claimed is not None
        assert claimed.id == job_id

    async def test_does_not_claim_a_retrying_job_whose_next_attempt_at_is_future(self, engine):
        future = sa.text("now() + interval '1 hour'")
        await _insert_job(
            engine,
            status=STATUS_RETRYING,
            attempts=1,
            started_at=sa.text("now()"),
            next_attempt_at=future,
        )
        async with build_sessionmaker(engine)() as session:
            claimed = await claim_next_due_job(session, now=datetime.now(UTC))
            await session.commit()
        assert claimed is None

    async def test_does_not_claim_running_completed_or_failed_jobs(self, engine):
        for status in (STATUS_RUNNING, STATUS_COMPLETED, "failed"):
            extra = {"attempts": 1, "started_at": sa.text("now()")}
            if status in (STATUS_COMPLETED, "failed"):
                extra["finished_at"] = sa.text("now()")
            await _insert_job(engine, status=status, **extra)
        async with build_sessionmaker(engine)() as session:
            claimed = await claim_next_due_job(session, now=datetime.now(UTC))
            await session.commit()
        assert claimed is None

    async def test_returns_none_when_nothing_is_due(self, engine):
        async with build_sessionmaker(engine)() as session:
            claimed = await claim_next_due_job(session, now=datetime.now(UTC))
        assert claimed is None

    async def test_claims_earliest_queued_at_first(self, engine):
        startup_a = await _insert_founder_with_startup(engine)
        startup_b = await _insert_founder_with_startup(engine)
        older_job_id, _ = await _insert_job(
            engine, startup_id=startup_a, queued_at=sa.text("now() - interval '1 hour'")
        )
        await _insert_job(engine, startup_id=startup_b, queued_at=sa.text("now()"))

        async with build_sessionmaker(engine)() as session:
            claimed = await claim_next_due_job(session, now=datetime.now(UTC))
            await session.commit()
        assert claimed.id == older_job_id


class TestConcurrentClaimsNeverOverlap:
    async def test_two_concurrent_claimers_get_two_distinct_jobs(self, engine):
        job_id_a, _ = await _insert_job(engine)
        job_id_b, _ = await _insert_job(engine)

        results: list[uuid.UUID | None] = [None, None]

        async def claim_and_hold(index: int, hold_seconds: float) -> None:
            async with build_sessionmaker(engine)() as session, session.begin():
                claimed = await claim_next_due_job(session, now=datetime.now(UTC))
                results[index] = claimed.id if claimed else None
                await asyncio.sleep(hold_seconds)

        await asyncio.gather(claim_and_hold(0, 0.2), claim_and_hold(1, 0.05))

        assert None not in results
        assert set(results) == {job_id_a, job_id_b}

    async def test_second_claimer_never_blocks_on_the_first(self, engine):
        await _insert_job(engine)

        async def hold_first() -> None:
            async with build_sessionmaker(engine)() as session, session.begin():
                await claim_next_due_job(session, now=datetime.now(UTC))
                await asyncio.sleep(0.3)

        first = asyncio.create_task(hold_first())
        await asyncio.sleep(0.05)  # let the first claim land and hold its lock

        async with build_sessionmaker(engine)() as session:
            start = asyncio.get_event_loop().time()
            claimed = await claim_next_due_job(session, now=datetime.now(UTC))
            elapsed = asyncio.get_event_loop().time() - start

        await first
        assert claimed is None  # the only job is locked by the first claimer
        assert elapsed < 0.2  # SKIP LOCKED returns immediately, never blocks
