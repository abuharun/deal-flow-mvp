"""Narrative-approval data access: at most one frozen version per startup.

No update or delete method exists here on purpose -- the table rejects direct
UPDATE/DELETE at the DB level (see migration 0013_narrative_approvals), and
the only write path is `insert_approval`. There is no un-approve in this
slice.

Every lookup is scoped by startup_id, and callers reach it only through a
founder-scoped `_load_owned_startup`, so one founder's approval can never be
read or created through another's startup.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NarrativeApproval, NarrativeVersion


async def get_for_startup(
    session: AsyncSession, *, startup_id: uuid.UUID
) -> NarrativeApproval | None:
    stmt = select(NarrativeApproval).where(NarrativeApproval.startup_id == startup_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_with_version(
    session: AsyncSession, *, startup_id: uuid.UUID
) -> tuple[NarrativeApproval, NarrativeVersion] | None:
    """The approval and the exact immutable version it froze, or None.

    Joined on narrative_version_id -- the row the approval's composite FK
    already pins to (this startup, that version number, that report) -- so
    this can only ever return the text that was actually approved.
    """
    stmt = (
        select(NarrativeApproval, NarrativeVersion)
        .join(NarrativeVersion, NarrativeVersion.id == NarrativeApproval.narrative_version_id)
        .where(NarrativeApproval.startup_id == startup_id)
    )
    row = (await session.execute(stmt)).one_or_none()
    return (row[0], row[1]) if row is not None else None


async def insert_approval(
    session: AsyncSession, *, approval: NarrativeApproval
) -> NarrativeApproval:
    """Stage one immutable approval; the caller owns the transaction.

    Flushed here so a duplicate approval (UNIQUE startup_id) and the
    database's own "must be the current version" guard both surface at the
    point of the write rather than at commit time.
    """
    session.add(approval)
    await session.flush()
    return approval
