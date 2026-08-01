"""Immutable AI-research-report data access.

No update/delete method exists here on purpose: both tables reject direct
UPDATE/DELETE at the DB level (see migration 0011_analysis_reports). The
only mutation path is `insert_report`, called once per (startup, job) by
`app.services.analysis_report_service`.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisReport, ReportSource


class ReportAlreadyExistsError(Exception):
    """A report already exists for this job; nothing was inserted or changed."""

    def __init__(self, existing: AnalysisReport) -> None:
        super().__init__(f"a report already exists for job {existing.job_id}")
        self.existing = existing


async def get_for_startup(session: AsyncSession, *, startup_id: uuid.UUID) -> AnalysisReport | None:
    stmt = select(AnalysisReport).where(AnalysisReport.startup_id == startup_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_for_job(session: AsyncSession, *, job_id: uuid.UUID) -> AnalysisReport | None:
    stmt = select(AnalysisReport).where(AnalysisReport.job_id == job_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_sources_for_report(
    session: AsyncSession, *, report_id: uuid.UUID
) -> list[ReportSource]:
    stmt = (
        select(ReportSource)
        .where(ReportSource.report_id == report_id)
        .order_by(ReportSource.ordinal)
    )
    return list((await session.execute(stmt)).scalars())


async def insert_report(
    session: AsyncSession, *, report: AnalysisReport, sources: list[ReportSource]
) -> AnalysisReport:
    """Stage one report and its sources; caller flushes/commits the transaction.

    Refuses (without touching anything) if a report already exists for this
    job_id -- the DB's UNIQUE constraints are the backstop, this is the
    typed, pre-flush guard.
    """
    existing = await get_for_job(session, job_id=report.job_id)
    if existing is not None:
        raise ReportAlreadyExistsError(existing)

    session.add(report)
    await session.flush()  # assigns report.id for the sources' FK
    for source in sources:
        source.report_id = report.id
    session.add_all(sources)
    await session.flush()
    return report
