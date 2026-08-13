"""Narrative data access: append-only history plus one current pointer.

No update or delete method for `NarrativeVersion` exists here on purpose --
the table rejects direct UPDATE/DELETE at the DB level (see migration
0012_narratives), and the only write path is `insert_version`. The single
mutable write in this module is `set_current_version`, which moves (or
first creates) the per-startup pointer.

Every lookup is scoped by startup_id, and callers reach it only through a
founder-scoped `_load_owned_startup`, so one founder's narrative can never
be read or advanced through another's startup.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NarrativeVersion, StartupNarrative

_VERSIONS = NarrativeVersion.__table__


async def get_current(session: AsyncSession, *, startup_id: uuid.UUID) -> StartupNarrative | None:
    stmt = select(StartupNarrative).where(StartupNarrative.startup_id == startup_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_current_with_version(
    session: AsyncSession, *, startup_id: uuid.UUID
) -> tuple[StartupNarrative, NarrativeVersion] | None:
    """The pointer and the version row it names, or None if never seeded.

    Joined on (startup_id, version) -- the same composite key the pointer's
    FK enforces -- so this can only ever return this startup's own text.
    """
    stmt = (
        select(StartupNarrative, NarrativeVersion)
        .join(
            NarrativeVersion,
            (NarrativeVersion.startup_id == StartupNarrative.startup_id)
            & (NarrativeVersion.version == StartupNarrative.current_version),
        )
        .where(StartupNarrative.startup_id == startup_id)
    )
    row = (await session.execute(stmt)).one_or_none()
    return (row[0], row[1]) if row is not None else None


async def get_version(
    session: AsyncSession, *, startup_id: uuid.UUID, version: int
) -> NarrativeVersion | None:
    stmt = select(NarrativeVersion).where(
        NarrativeVersion.startup_id == startup_id, NarrativeVersion.version == version
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_version_summaries(session: AsyncSession, *, startup_id: uuid.UUID) -> list[Row]:
    """History metadata in ascending version order -- never the text itself.

    `content` is projected only as its length: a history listing must stay
    cheap no matter how long each revision is, and the full text belongs to
    the single-version read.
    """
    stmt = (
        select(
            _VERSIONS.c.version,
            _VERSIONS.c.source,
            _VERSIONS.c.report_id,
            _VERSIONS.c.input_revision,
            func.char_length(_VERSIONS.c.content).label("content_length"),
            _VERSIONS.c.created_at,
        )
        .where(_VERSIONS.c.startup_id == startup_id)
        .order_by(_VERSIONS.c.version)
    )
    return list((await session.execute(stmt)).all())


async def insert_version(session: AsyncSession, *, version: NarrativeVersion) -> NarrativeVersion:
    """Stage one immutable version; the caller owns the transaction.

    Flushed here so the row exists before the current pointer's composite FK
    is checked, and so a duplicate (startup_id, version) surfaces at the
    point of the write rather than at commit time.
    """
    session.add(version)
    await session.flush()
    return version


async def set_current_version(
    session: AsyncSession, *, startup_id: uuid.UUID, version: int
) -> StartupNarrative:
    """Point the startup at `version`, creating the pointer row on first use."""
    current = await get_current(session, startup_id=startup_id)
    if current is None:
        current = StartupNarrative(startup_id=startup_id, current_version=version)
        session.add(current)
    else:
        current.current_version = version
    await session.flush()
    return current
