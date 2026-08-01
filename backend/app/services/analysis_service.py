"""Founder AI-analysis job trigger + status.

Transaction contract (same as the other services): every function stages
rows and flushes but never commits -- the endpoint owns the boundary, so a
newly queued job, the startup's analyzing transition, and its audit row
commit or roll back together.

Product contract: at most one current job per startup for this pilot.
Triggering is idempotent -- a second call while a job already exists
(queued, running, retrying, completed, or failed) returns that SAME job
unchanged; it never resets status/attempts and never creates a second row
or a second audit entry, and the startup's status/input_revision are left
untouched on that path. This module never calls OpenAI, never reads deck
bytes (only metadata), and never logs founder answers, URLs, or PDF data.

Audit hygiene: metadata carries only startup_id/job_id/input_revision/status
(and prompt_version when the job already has one) -- never a private value.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisJob, AuditActorType, Startup, StartupStatus
from app.models.analysis_job import DEFAULT_MAX_ATTEMPTS, STATUS_QUEUED
from app.repositories import analysis_repository, payment_repository
from app.repositories.deck_repository import PostgresDeckStorage
from app.services.ai_precondition import AiPreconditionReason, evaluate_ai_preconditions
from app.services.audit_service import write_audit
from app.services.consent_service import current_ai_privacy_consent_granted
from app.services.startup_service import StartupLockedError, is_locked

# Startup statuses eligible to trigger analysis: never a draft. VC-visible is
# refused earlier (as the canonical STARTUP_LOCKED 409), never reaching here.
_ELIGIBLE_STARTUP_STATUSES = frozenset(
    {StartupStatus.SUBMITTED, StartupStatus.ANALYZING, StartupStatus.REPORT_READY}
)


class AnalysisPreconditionError(Exception):
    """Trigger was refused; carries only the MISSING reason codes, deterministic order."""

    def __init__(self, missing: tuple[AiPreconditionReason, ...]) -> None:
        super().__init__("analysis preconditions not met")
        self.missing = missing


class AnalysisNotFoundError(Exception):
    """The founder's startup exists but has no analysis job yet."""


async def _audit_trigger(session: AsyncSession, startup: Startup, job: AnalysisJob) -> None:
    metadata: dict[str, object] = {
        "startup_id": str(startup.id),
        "job_id": str(job.id),
        "input_revision": job.input_revision,
        "status": job.status,
    }
    if job.prompt_version is not None:
        metadata["prompt_version"] = job.prompt_version
    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        actor_id=startup.founder_id,
        action="startup.analysis_trigger",
        entity_type="startup",
        entity_id=startup.id,
        metadata=metadata,
    )


async def trigger_analysis(session: AsyncSession, *, startup: Startup) -> tuple[AnalysisJob, bool]:
    """Validate prerequisites and atomically create (or idempotently return) the job.

    Returns (job, created). Caller must have loaded `startup` with a row
    lock (`_load_owned_startup(..., for_update=True)`) so concurrent
    triggers for the same startup serialize on that lock; the UNIQUE
    startup_id constraint on analysis_jobs is the DB-level backstop.
    """
    if is_locked(startup):
        raise StartupLockedError

    existing = await analysis_repository.get_for_startup(session, startup_id=startup.id)
    if existing is not None:
        return existing, False

    deck_exists = (await PostgresDeckStorage(session).get_metadata(startup.id)) is not None
    payment = await payment_repository.get_for_startup(session, startup_id=startup.id)
    consent_granted = await current_ai_privacy_consent_granted(session, startup=startup)

    result = evaluate_ai_preconditions(
        startup_submitted=startup.status in _ELIGIBLE_STARTUP_STATUSES,
        deck_exists=deck_exists,
        payment_status=payment.status if payment is not None else None,
        consent_granted=consent_granted,
    )
    if not result.eligible:
        raise AnalysisPreconditionError(result.missing)

    job = AnalysisJob(
        startup_id=startup.id,
        input_revision=startup.input_revision,
        status=STATUS_QUEUED,
        attempts=0,
        max_attempts=DEFAULT_MAX_ATTEMPTS,
    )
    session.add(job)
    startup.status = StartupStatus.ANALYZING
    await session.flush()
    await session.refresh(job)
    await _audit_trigger(session, startup, job)
    return job, True


async def get_analysis_status(
    session: AsyncSession, *, startup: Startup
) -> tuple[AnalysisJob, bool]:
    """Current job plus `stale` = job.input_revision != startup.input_revision."""
    job = await analysis_repository.get_for_startup(session, startup_id=startup.id)
    if job is None:
        raise AnalysisNotFoundError
    return job, job.input_revision != startup.input_revision
