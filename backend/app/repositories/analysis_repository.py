"""Analysis job data access: at most one current job per startup.

Concurrency note: the trigger path mutates a job only after locking the
parent startup row with `_load_owned_startup(..., for_update=True)` (the
same pattern payment_repository and consent_repository rely on), so a plain
check-then-insert in the service is race-safe there. The worker's
state-machine transitions instead lock the job row itself via
`get_for_update`.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisJob


async def get_for_startup(session: AsyncSession, *, startup_id: uuid.UUID) -> AnalysisJob | None:
    stmt = select(AnalysisJob).where(AnalysisJob.startup_id == startup_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_for_update(session: AsyncSession, *, job_id: uuid.UUID) -> AnalysisJob | None:
    """Row-locked load for the worker's state-machine transitions."""
    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()
