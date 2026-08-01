"""Startup/submission data access.

Every lookup is scoped by founder_id at the SQL level: a startup another
founder owns is indistinguishable from one that does not exist, which is what
lets the API answer a uniform 404 without ever comparing ownership in Python.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Startup


async def get_owned_startup(
    session: AsyncSession,
    *,
    startup_id: uuid.UUID,
    founder_id: uuid.UUID,
    with_submission: bool = False,
    for_update: bool = False,
) -> Startup | None:
    """The founder's startup, or None for unknown AND foreign ids alike."""
    stmt = select(Startup).where(Startup.id == startup_id, Startup.founder_id == founder_id)
    if with_submission:
        stmt = stmt.options(selectinload(Startup.submission))
    if for_update:
        # Serializes concurrent mutations of one startup so input_revision
        # can only ever move forward by exactly one per transaction.
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_for_update(
    session: AsyncSession, *, startup_id: uuid.UUID, with_submission: bool = False
) -> Startup | None:
    """Row-locked load for the worker: no founder scoping.

    The job already identifies the startup unambiguously (analysis_jobs.
    startup_id), so unlike get_owned_startup this never takes a founder_id --
    the worker is a system actor, not acting on behalf of one specific user.
    """
    stmt = select(Startup).where(Startup.id == startup_id).with_for_update()
    if with_submission:
        stmt = stmt.options(selectinload(Startup.submission))
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_startups_for_founder(
    session: AsyncSession, *, founder_id: uuid.UUID
) -> list[Startup]:
    stmt = (
        select(Startup)
        .where(Startup.founder_id == founder_id)
        .order_by(Startup.created_at.desc(), Startup.id.desc())
    )
    return list((await session.execute(stmt)).scalars())
