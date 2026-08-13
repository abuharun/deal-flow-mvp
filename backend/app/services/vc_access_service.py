"""What an active pilot VC account may read, and nothing more.

Product contract: a startup reaches investors because its founder approved a
narrative version -- see app.services.narrative_approval_service, which is
the only thing that creates an approval and flips the startup to VC-visible.
This module is the read side of that act and does exactly two things: page
the approved startups, and assemble one approved startup's dossier.

Access model in this slice: ALL active pilot VC accounts see the SAME
startups. There is no per-investor assignment, so nothing here takes a
viewer id; "active/verified" is the canonical auth policy already enforced
in `get_current_principal`, not a second rule invented here.

Transaction contract: read-only. Nothing in this module stages a row,
writes an audit event, or takes a lock -- an investor reading a dossier must
not be able to change a single byte of what a founder froze.

Not found means "not approved for you to see": unknown, unapproved, and
not-yet-visible ids all raise the one `StartupNotVisibleError`, which the
router turns into the same canonical 404 the founder surface uses. Whether a
startup exists at all is not an investor's business.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisReport,
    NarrativeApproval,
    NarrativeVersion,
    ReportSource,
    Startup,
)
from app.repositories import analysis_report_repository, vc_repository

__all__ = [
    "StartupNotVisibleError",
    "VisibleStartupPage",
    "get_startup_dossier",
    "list_visible_startups",
]


class StartupNotVisibleError(Exception):
    """No approved, VC-visible startup carries this id (unknown or unapproved)."""


@dataclass(frozen=True, slots=True)
class VisibleStartupPage:
    """One page of (startup, approved_at) pairs plus the total behind it.

    The pairs arrive already ordered by the repository; nothing re-sorts them
    in Python, so the API's order is the SQL order.
    """

    rows: list[tuple[Startup, datetime]]
    total: int


async def list_visible_startups(
    session: AsyncSession, *, limit: int, offset: int
) -> VisibleStartupPage:
    """One deterministic page of approved startups, newest approval first.

    Two queries regardless of page size: the page itself and its count. The
    count is what lets a client page without probing for the end.
    """
    rows = await vc_repository.list_visible_startups(session, limit=limit, offset=offset)
    total = await vc_repository.count_visible_startups(session)
    return VisibleStartupPage(rows=[(row[0], row[1]) for row in rows], total=total)


async def get_startup_dossier(
    session: AsyncSession, *, startup_id: uuid.UUID
) -> tuple[Startup, NarrativeApproval, NarrativeVersion, AnalysisReport, list[ReportSource]]:
    """Everything one approved startup's dossier is built from.

    Two queries: the joined startup/approval/version/report row, then the
    report's sources in ordinal order. Raises StartupNotVisibleError for
    unknown, unapproved, and not-yet-visible ids alike.
    """
    row = await vc_repository.get_visible_startup_dossier(session, startup_id=startup_id)
    if row is None:
        raise StartupNotVisibleError
    startup, approval, version, report = row
    sources = await analysis_report_repository.get_sources_for_report(session, report_id=report.id)
    return startup, approval, version, report, sources
