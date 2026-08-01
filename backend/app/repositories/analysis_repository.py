"""Analysis job data access: at most one current job per startup.

Concurrency note: the trigger path mutates a job only after locking the
parent startup row with `_load_owned_startup(..., for_update=True)` (the
same pattern payment_repository and consent_repository rely on), so a plain
check-then-insert in the service is race-safe there. The worker's
state-machine transitions instead lock the job row itself via
`get_for_update`; claiming the NEXT due job across all startups uses
`claim_next_due_job` (`FOR UPDATE SKIP LOCKED`) so concurrent worker
processes never block on, or double-claim, one another's row.
"""

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisJob
from app.models.analysis_job import STATUS_QUEUED, STATUS_RETRYING, STATUS_RUNNING


async def get_for_startup(session: AsyncSession, *, startup_id: uuid.UUID) -> AnalysisJob | None:
    stmt = select(AnalysisJob).where(AnalysisJob.startup_id == startup_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_for_update(session: AsyncSession, *, job_id: uuid.UUID) -> AnalysisJob | None:
    """Row-locked load for the worker's state-machine transitions."""
    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def claim_next_due_job(session: AsyncSession, *, now: datetime) -> AnalysisJob | None:
    """Lock and return one due queued/retrying job, or None if nothing is due.

    `FOR UPDATE SKIP LOCKED` means a job another worker already holds the
    row lock on is invisible to this query rather than something we'd block
    on -- two workers polling concurrently each get a DIFFERENT job (or
    None), never the same one twice. Ordering is deterministic (queued_at,
    then id as a tiebreaker) so claims are FIFO across worker processes.
    """
    stmt = (
        select(AnalysisJob)
        .where(
            AnalysisJob.status.in_((STATUS_QUEUED, STATUS_RETRYING)),
            or_(AnalysisJob.next_attempt_at.is_(None), AnalysisJob.next_attempt_at <= now),
        )
        .order_by(AnalysisJob.queued_at.asc(), AnalysisJob.id.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def claim_stale_running_job(session: AsyncSession, *, now: datetime) -> AnalysisJob | None:
    """Lock and return one RUNNING job whose deadline has passed, or None.

    Recovers jobs left stuck RUNNING by a worker process that crashed or was
    killed mid-attempt. `SKIP LOCKED` (same as claim_next_due_job) means two
    recovery sweeps running concurrently never grab the same stale job.
    """
    stmt = (
        select(AnalysisJob)
        .where(
            AnalysisJob.status == STATUS_RUNNING,
            AnalysisJob.deadline_at.is_not(None),
            AnalysisJob.deadline_at <= now,
        )
        .order_by(AnalysisJob.queued_at.asc(), AnalysisJob.id.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()
