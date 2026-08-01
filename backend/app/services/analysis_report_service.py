"""Atomic completion of an AI-analysis job into an immutable, cited report.

Transaction contract (same as every other service in this codebase): stages
the report row, its normalized sources, the job's completed transition, the
startup's report_ready transition, and the audit row, then flushes but never
commits -- the caller owns the transaction boundary, so a report can never
exist without its job being completed and the startup moving to
report_ready, and a failure at any point leaves the job RUNNING with no
partial report/sources.

Callers of `complete_job_with_report` must already hold row locks on both
`job` (analysis_repository.get_for_update) and `startup` (startup_repository.
get_owned_startup(..., for_update=True)) -- the same pattern every other
trigger/transition path in this codebase uses. There is no public HTTP
endpoint that reaches `complete_job_with_report` in this slice, and it never
calls OpenAI or any other provider: a future worker (or a test standing in
for one) is the only caller. `get_report_for_startup`, by contrast, backs the
founder-only read endpoint (GET /founder/startups/{id}/report) -- it is
read-only and takes no lock.

Audit hygiene: metadata carries only startup_id/report_id/job_id/
input_revision/model/prompt_version/partial/evidence_count -- never report
text, citation snippets, or source URLs.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisReport, AuditActorType, ReportSource, Startup, StartupStatus
from app.models.analysis_job import STATUS_RUNNING, AnalysisJob
from app.models.analysis_report import MAX_MODEL_LENGTH, MAX_PROMPT_VERSION_LENGTH
from app.repositories import analysis_report_repository
from app.repositories.analysis_report_repository import ReportAlreadyExistsError
from app.schemas.analysis import AnalysisCompletionInput
from app.schemas.report import ReportV1Input
from app.services import analysis_state
from app.services.audit_service import write_audit

__all__ = [
    "InputRevisionMismatchError",
    "JobMismatchError",
    "JobNotRunningError",
    "ReportAlreadyExistsError",
    "ReportNotFoundError",
    "complete_job_with_report",
    "get_report_for_startup",
]


class ReportNotFoundError(Exception):
    """The founder's startup exists but carries no report yet."""


class JobMismatchError(Exception):
    """The supplied job does not belong to the supplied startup."""


class InputRevisionMismatchError(Exception):
    """The job's input_revision doesn't match the caller's declared value, or
    the startup has moved past it (a founder edit landed after the job
    started) -- either way the job's would-be report is against stale
    input and must not complete."""


class JobNotRunningError(Exception):
    """The job is not RUNNING -- the only legal state a report can complete from."""

    def __init__(self, actual_status: str) -> None:
        super().__init__(f"job is {actual_status!r}, not 'running'")
        self.actual_status = actual_status


def _validate_bounded_nonempty(value: str, *, name: str, max_length: int) -> None:
    if not value or len(value) > max_length:
        raise ValueError(f"{name} must be 1..{max_length} characters, got {value!r}")


async def complete_job_with_report(
    session: AsyncSession,
    *,
    job: AnalysisJob,
    startup: Startup,
    input_revision: int,
    report_input: ReportV1Input,
    model: str,
    prompt_version: str,
    generated_at: datetime,
    partial: bool = False,
) -> AnalysisReport:
    """Validate everything, then insert the report+sources and complete the job.

    Every validation happens before the first `session.add`, so a rejected
    call never stages anything a caller would need to roll back.
    """
    if job.startup_id != startup.id:
        raise JobMismatchError
    if input_revision != job.input_revision:
        raise InputRevisionMismatchError
    if startup.input_revision != job.input_revision:
        raise InputRevisionMismatchError
    if job.status != STATUS_RUNNING:
        raise JobNotRunningError(job.status)
    _validate_bounded_nonempty(model, name="model", max_length=MAX_MODEL_LENGTH)
    _validate_bounded_nonempty(
        prompt_version, name="prompt_version", max_length=MAX_PROMPT_VERSION_LENGTH
    )

    report_row = AnalysisReport(
        startup_id=startup.id,
        job_id=job.id,
        input_revision=job.input_revision,
        schema_version=report_input.schema_version,
        language=report_input.language,
        report=report_input.report.model_dump(mode="json"),
        model=model,
        prompt_version=prompt_version,
        partial=partial,
        evidence_count=len(report_input.sources),
        generated_at=generated_at,
    )
    source_rows = [
        ReportSource(
            ordinal=ordinal,
            url=source.url,
            title=source.title,
            published_date=source.published_date,
            accessed_date=source.accessed_date,
            source_quality=source.source_quality,
            confidence=source.confidence,
            snippet=source.snippet,
        )
        for ordinal, source in enumerate(report_input.sources, start=1)
    ]

    # May raise ReportAlreadyExistsError -- nothing above this line touches
    # the session, so a duplicate call never mutates the existing report.
    await analysis_report_repository.insert_report(session, report=report_row, sources=source_rows)

    analysis_state.mark_completed(
        job, completion=AnalysisCompletionInput(model=model, prompt_version=prompt_version)
    )
    startup.status = StartupStatus.REPORT_READY

    await write_audit(
        session,
        actor_type=AuditActorType.WORKER,
        action="startup.report_completed",
        entity_type="startup",
        entity_id=startup.id,
        metadata={
            "startup_id": str(startup.id),
            "report_id": str(report_row.id),
            "job_id": str(job.id),
            "input_revision": report_row.input_revision,
            "model": model,
            "prompt_version": prompt_version,
            "partial": partial,
            "evidence_count": report_row.evidence_count,
        },
    )
    return report_row


async def get_report_for_startup(
    session: AsyncSession, *, startup: Startup
) -> tuple[AnalysisReport, list[ReportSource], bool]:
    """The startup's report plus its sources and `stale`.

    `stale` = report.input_revision != startup.input_revision, computed at
    read time (never stored) -- a founder edit after generation never
    mutates the report, it only changes whether a future read sees it as
    fresh. Raises ReportNotFoundError if no report exists yet.
    """
    report = await analysis_report_repository.get_for_startup(session, startup_id=startup.id)
    if report is None:
        raise ReportNotFoundError
    sources = await analysis_report_repository.get_sources_for_report(session, report_id=report.id)
    return report, sources, report.input_revision != startup.input_revision
