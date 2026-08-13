"""Read-only data access for the investor surface.

Two rules hold for every query here, and they are enforced in SQL rather
than in Python so no caller can forget them:

1. Visibility is the AND of "the startup says vc_visible" and "an approval
   row exists". The approval is what the founder actually did; the status is
   the state that act produced. Requiring both means a status forced by hand
   (or by a future code path) still shows nothing without the founder's
   approval behind it.
2. Nothing is per-investor. Every active pilot VC account sees the same set,
   so no query here takes a viewer id -- there is no audience model to get
   wrong in this slice.

There is no insert/update/delete in this module on purpose: the investor
surface is read-only.

Query shape: the list is one page query plus one count, and the dossier is a
single four-way join plus one ordered fetch of the report's sources -- never
a per-row follow-up.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisReport,
    NarrativeApproval,
    NarrativeVersion,
    Startup,
    StartupStatus,
)


def _visible():
    """startups JOIN narrative_approvals, restricted to approved + visible."""
    return (
        select(Startup)
        .join(NarrativeApproval, NarrativeApproval.startup_id == Startup.id)
        .where(Startup.status == StartupStatus.VC_VISIBLE)
    )


async def list_visible_startups(
    session: AsyncSession, *, limit: int, offset: int
) -> list[Row[tuple[Startup, object]]]:
    """One page of (startup, approved_at), newest approval first.

    The (approved_at DESC, id DESC) order is a total order -- id breaks any
    tie -- so paging can never skip or repeat a row.
    """
    stmt = (
        _visible()
        .add_columns(NarrativeApproval.approved_at)
        .order_by(NarrativeApproval.approved_at.desc(), Startup.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).all())


async def count_visible_startups(session: AsyncSession) -> int:
    stmt = (
        select(func.count())
        .select_from(Startup)
        .join(NarrativeApproval, NarrativeApproval.startup_id == Startup.id)
        .where(Startup.status == StartupStatus.VC_VISIBLE)
    )
    return int((await session.execute(stmt)).scalar_one())


async def get_visible_startup_dossier(
    session: AsyncSession, *, startup_id: uuid.UUID
) -> Row[tuple[Startup, NarrativeApproval, NarrativeVersion, AnalysisReport]] | None:
    """The startup, its approval, the frozen version, and the report -- or None.

    None covers unknown, unapproved, and not-yet-visible ids alike, which is
    what lets the router answer one indistinguishable 404.

    The version is joined by the id the approval names, and the report by the
    approval's own report_id: both are pinned by the approval's composite FK
    (see app.models.narrative_approval), so this can only ever return the
    exact text that was approved and the report it was written against.
    """
    stmt = (
        _visible()
        .add_columns(NarrativeApproval, NarrativeVersion, AnalysisReport)
        .join(NarrativeVersion, NarrativeVersion.id == NarrativeApproval.narrative_version_id)
        .join(AnalysisReport, AnalysisReport.id == NarrativeApproval.report_id)
        .where(Startup.id == startup_id)
    )
    return (await session.execute(stmt)).one_or_none()
