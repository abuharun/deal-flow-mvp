"""Claim/execute lifecycle for the OpenAI analysis worker.

Two-transaction shape, on purpose:
1. `_claim_and_prepare` claims one due job (`FOR UPDATE SKIP LOCKED`,
   deterministic order), locks its startup, builds the input snapshot, and
   transitions the job to RUNNING -- all in one short transaction that
   commits (and releases every lock) BEFORE the slow network call happens.
2. The provider call (`app.services.openai_provider.run_analysis`) then runs
   with NO open transaction and NO held row lock.
3. `_finalize_success`/`_finalize_failure` reopen a transaction, reacquire
   the job/startup locks, and verify the job is still RUNNING with the SAME
   attempt number and input_revision before writing anything -- if a founder
   edit or anything else moved the goalposts while the provider call was in
   flight, the result is discarded and the job is failed safely; a report is
   never persisted against stale input.

Retry policy: only `ProviderError.retryable` errors get another attempt, up
to `AnalysisJob.max_attempts` (currently 3), with bounded exponential
backoff. Every other failure (auth/config/budget/invalid-output/precondition)
is terminal on the first attempt. There is never more than one provider call
per attempt -- retrying means a LATER call to this module's entrypoint, not a
loop inside it.

Every failure/retry is recorded through a fixed, safe error_code/
message_key allowlist (`_ERROR_CATALOG`) -- never a raw provider or database
exception string.
"""

import asyncio
import contextlib
import enum
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Startup
from app.models.analysis_job import STATUS_RUNNING, AnalysisJob
from app.repositories import analysis_repository, startup_repository
from app.repositories.deck_repository import PostgresDeckStorage
from app.services import analysis_state
from app.services.analysis_report_service import complete_job_with_report
from app.services.analysis_snapshot import AnalysisInputSnapshot, SnapshotError, build_snapshot
from app.services.analysis_worker_config import WorkerConfig
from app.services.openai_provider import (
    ProviderError,
    ProviderResult,
    ResponsesClient,
    run_analysis,
)

# Deadline given to one attempt: the provider request's own timeout plus
# headroom for DB/lock round-trips, so a healthy attempt (even one that
# takes the full configured timeout) never looks "stale" to the recovery
# sweep -- see _claim_and_prepare, where this is added to config.
# request_timeout_seconds rather than used as a fixed value.
_DEADLINE_BUFFER_SECONDS = 60.0

# How often to refresh heartbeat_at while a provider call is in flight.
_DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 20.0

# Bounded exponential backoff for a retryable failure: 30s, 60s, ... capped.
_BASE_BACKOFF_SECONDS = 30.0
_MAX_BACKOFF_SECONDS = 900.0

# Fixed, safe (error_code, message_key) pairs -- see app.schemas.analysis for
# the exact charset each must satisfy. Never derived from provider/exception
# text; any unrecognized reason falls back to the last, generic entry.
_ERROR_CATALOG: dict[str, tuple[str, str]] = {
    "auth_error": ("PROVIDER_AUTH_ERROR", "analysis.providerAuthError"),
    "rate_limited": ("PROVIDER_RATE_LIMITED", "analysis.providerRateLimited"),
    "timeout": ("PROVIDER_TIMEOUT", "analysis.providerTimeout"),
    "server_error": ("PROVIDER_SERVER_ERROR", "analysis.providerServerError"),
    "network_error": ("PROVIDER_NETWORK_ERROR", "analysis.providerNetworkError"),
    "provider_rejected_request": (
        "PROVIDER_REJECTED_REQUEST",
        "analysis.providerRejectedRequest",
    ),
    "provider_error": ("PROVIDER_ERROR", "analysis.providerError"),
    "invalid_output": ("PROVIDER_INVALID_OUTPUT", "analysis.providerInvalidOutput"),
    "usage_invalid": ("PROVIDER_USAGE_INVALID", "analysis.providerUsageInvalid"),
    "budget_exceeded": ("PROVIDER_BUDGET_EXCEEDED", "analysis.providerBudgetExceeded"),
    "schema_version_mismatch": (
        "PROVIDER_SCHEMA_VERSION_MISMATCH",
        "analysis.providerSchemaVersionMismatch",
    ),
    "job_startup_mismatch": ("SNAPSHOT_JOB_MISMATCH", "analysis.snapshotJobMismatch"),
    "input_revision_mismatch": (
        "SNAPSHOT_INPUT_REVISION_MISMATCH",
        "analysis.snapshotInputRevisionMismatch",
    ),
    "consent_missing": ("SNAPSHOT_CONSENT_MISSING", "analysis.snapshotConsentMissing"),
    "payment_not_paid": ("SNAPSHOT_PAYMENT_NOT_PAID", "analysis.snapshotPaymentNotPaid"),
    "deck_missing": ("SNAPSHOT_DECK_MISSING", "analysis.snapshotDeckMissing"),
    "deck_encrypted": ("SNAPSHOT_DECK_ENCRYPTED", "analysis.snapshotDeckEncrypted"),
    "deck_malformed": ("SNAPSHOT_DECK_MALFORMED", "analysis.snapshotDeckMalformed"),
    "deck_no_extractable_text": (
        "SNAPSHOT_DECK_NO_TEXT",
        "analysis.snapshotDeckNoText",
    ),
    "deck_too_large": ("SNAPSHOT_DECK_TOO_LARGE", "analysis.snapshotDeckTooLarge"),
    "deck_page_count": ("SNAPSHOT_DECK_PAGE_COUNT", "analysis.snapshotDeckPageCount"),
    "stale_result_discarded": (
        "STALE_RESULT_DISCARDED",
        "analysis.staleResultDiscarded",
    ),
    "max_attempts_exceeded": ("MAX_ATTEMPTS_EXCEEDED", "analysis.maxAttemptsExceeded"),
    "startup_missing": ("STARTUP_MISSING", "analysis.startupMissing"),
    "worker_unexpected_error": (
        "WORKER_UNEXPECTED_ERROR",
        "analysis.workerUnexpectedError",
    ),
}


def _catalog(reason: str) -> tuple[str, str]:
    return _ERROR_CATALOG.get(reason, _ERROR_CATALOG["worker_unexpected_error"])


def _retry_backoff_seconds(attempt: int) -> float:
    return min(_BASE_BACKOFF_SECONDS * (2 ** max(attempt - 1, 0)), _MAX_BACKOFF_SECONDS)


class JobOutcome(enum.Enum):
    NO_JOB_DUE = "no_job_due"
    SUCCEEDED = "succeeded"
    RETRYING = "retrying"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WorkResult:
    outcome: JobOutcome
    job_id: uuid.UUID | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class _ClaimedAttempt:
    job_id: uuid.UUID
    startup_id: uuid.UUID
    attempt: int
    input_revision: int
    max_attempts: int
    snapshot: AnalysisInputSnapshot


SessionFactory = async_sessionmaker[AsyncSession]


async def _claim_and_prepare(
    sessionmaker: SessionFactory, *, now: datetime, config: WorkerConfig
) -> _ClaimedAttempt | WorkResult | None:
    """Claim one due job and build its snapshot, or fail it safely in place.

    Returns None if nothing is due, a WorkResult(FAILED) if the job was
    claimed but a precondition was no longer met (committed, terminal), or a
    _ClaimedAttempt ready for a provider call.
    """
    async with sessionmaker() as session, session.begin():
        job = await analysis_repository.claim_next_due_job(session, now=now)
        if job is None:
            return None

        startup = await startup_repository.get_for_update(
            session, startup_id=job.startup_id, with_submission=True
        )
        if startup is None:
            # The job's startup is gone (should be impossible given the FK's
            # ON DELETE CASCADE, but never assume that from here): fail safely
            # rather than dereference a None a few lines down.
            code, key = _catalog("startup_missing")
            analysis_state.start_running(job)
            analysis_state.mark_failed(job, error_code=code, error_message_key=key)
            return WorkResult(JobOutcome.FAILED, job_id=job.id, error_code=code)

        try:
            deadline_at = now + timedelta(
                seconds=config.request_timeout_seconds + _DEADLINE_BUFFER_SECONDS
            )
            analysis_state.start_running(job, deadline_at=deadline_at)
        except analysis_state.MaxAttemptsExceededError:
            code, key = _catalog("max_attempts_exceeded")
            analysis_state.mark_failed(job, error_code=code, error_message_key=key)
            return WorkResult(JobOutcome.FAILED, job_id=job.id, error_code=code)

        try:
            snapshot = await build_snapshot(
                session, job=job, startup=startup, deck_storage=PostgresDeckStorage(session)
            )
        except SnapshotError as exc:
            code, key = _catalog(exc.reason)
            analysis_state.mark_failed(job, error_code=code, error_message_key=key)
            return WorkResult(JobOutcome.FAILED, job_id=job.id, error_code=code)

        return _ClaimedAttempt(
            job_id=job.id,
            startup_id=startup.id,
            attempt=job.attempts,
            input_revision=job.input_revision,
            max_attempts=job.max_attempts,
            snapshot=snapshot,
        )


async def _reacquire_matching(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    startup_id: uuid.UUID,
    attempt: int,
    input_revision: int,
) -> tuple[AnalysisJob | None, Startup | None, bool]:
    """Lock job+startup once; report whether this is still the SAME
    in-flight attempt. Callers use the returned job/startup directly --
    never re-query them -- so there is exactly one lock/query pair per
    finalize call."""
    job = await analysis_repository.get_for_update(session, job_id=job_id)
    startup = await startup_repository.get_for_update(session, startup_id=startup_id)
    if job is None or startup is None:
        return job, startup, False
    still_matches = (
        job.status == STATUS_RUNNING
        and job.attempts == attempt
        and job.input_revision == input_revision
        and startup.input_revision == input_revision
    )
    return job, startup, still_matches


def _discard_stale(job: AnalysisJob | None, *, attempt: int, job_id: uuid.UUID) -> WorkResult:
    """Terminal-fail the still-RUNNING same attempt if that's why matching
    failed (input revision drifted under it); a no-op if someone else
    already finalized this attempt or the job/startup is gone -- either way,
    nothing here is ever left RUNNING with no path back to a terminal state.
    """
    code, key = _catalog("stale_result_discarded")
    if job is not None and job.status == STATUS_RUNNING and job.attempts == attempt:
        analysis_state.mark_failed(job, error_code=code, error_message_key=key)
    return WorkResult(JobOutcome.FAILED, job_id=job_id, error_code=code)


async def _finalize_success(
    sessionmaker: SessionFactory,
    *,
    job_id: uuid.UUID,
    startup_id: uuid.UUID,
    attempt: int,
    input_revision: int,
    result: ProviderResult,
    prompt_version: str,
) -> WorkResult:
    async with sessionmaker() as session, session.begin():
        job, startup, still_matches = await _reacquire_matching(
            session,
            job_id=job_id,
            startup_id=startup_id,
            attempt=attempt,
            input_revision=input_revision,
        )
        if not still_matches:
            return _discard_stale(job, attempt=attempt, job_id=job_id)

        await complete_job_with_report(
            session,
            job=job,
            startup=startup,
            input_revision=input_revision,
            report_input=result.report_input,
            model=result.model,
            prompt_version=prompt_version,
            generated_at=result.generated_at,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_estimate_usd=result.cost_estimate_usd,
        )
        return WorkResult(JobOutcome.SUCCEEDED, job_id=job_id)


async def _finalize_failure(
    sessionmaker: SessionFactory,
    *,
    job_id: uuid.UUID,
    startup_id: uuid.UUID,
    attempt: int,
    input_revision: int,
    error: ProviderError,
    now: datetime,
) -> WorkResult:
    async with sessionmaker() as session, session.begin():
        job, _startup, still_matches = await _reacquire_matching(
            session,
            job_id=job_id,
            startup_id=startup_id,
            attempt=attempt,
            input_revision=input_revision,
        )
        if not still_matches:
            return _discard_stale(job, attempt=attempt, job_id=job_id)

        code, key = _catalog(error.code)
        if error.retryable and job.attempts < job.max_attempts:
            next_attempt_at = now + timedelta(seconds=_retry_backoff_seconds(job.attempts))
            analysis_state.mark_retrying(
                job, next_attempt_at=next_attempt_at, error_code=code, error_message_key=key
            )
            return WorkResult(JobOutcome.RETRYING, job_id=job_id, error_code=code)

        analysis_state.mark_failed(job, error_code=code, error_message_key=key)
        return WorkResult(JobOutcome.FAILED, job_id=job_id, error_code=code)


async def _fail_best_effort(
    sessionmaker: SessionFactory, *, job_id: uuid.UUID, attempt: int
) -> WorkResult:
    """Best-effort terminal-fail after an UNEXPECTED (non-ProviderError,
    non-SnapshotError) exception. Swallows any secondary failure here on
    purpose: a bug marking the job failed must never mask, or replace, the
    original unexpected error as the reported outcome."""
    code, key = _catalog("worker_unexpected_error")
    with contextlib.suppress(Exception):
        async with sessionmaker() as session, session.begin():
            job = await analysis_repository.get_for_update(session, job_id=job_id)
            if job is not None and job.status == STATUS_RUNNING and job.attempts == attempt:
                analysis_state.mark_failed(job, error_code=code, error_message_key=key)
    return WorkResult(JobOutcome.FAILED, job_id=job_id, error_code=code)


async def _heartbeat_loop(
    sessionmaker: SessionFactory,
    *,
    job_id: uuid.UUID,
    attempt: int,
    input_revision: int,
    interval_seconds: float,
) -> None:
    """While a provider call is in flight, periodically refresh heartbeat_at
    so liveness is visible without a second concurrent provider call ever
    happening -- this loop only ever touches `heartbeat_at`, never a status
    transition; finalize alone owns those. Stops touching the row (silently,
    without failing anything) once it's no longer this exact in-flight
    attempt -- e.g. finalize already completed it from a prior, unrelated
    call path. Intended to be cancelled by its caller once the provider call
    returns; a cancellation here is expected, not an error.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        async with sessionmaker() as session, session.begin():
            job = await analysis_repository.get_for_update(session, job_id=job_id)
            if (
                job is None
                or job.status != STATUS_RUNNING
                or job.attempts != attempt
                or job.input_revision != input_revision
            ):
                return
            job.heartbeat_at = datetime.now(UTC)


async def run_one_job(
    sessionmaker: SessionFactory,
    *,
    client: ResponsesClient,
    config: WorkerConfig,
    now: datetime | None = None,
    heartbeat_interval_seconds: float = _DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> WorkResult:
    """Claim and fully process at most one due job. Never raises -- every
    outcome, including a bug in this module itself, is reported, not thrown."""
    at = now or datetime.now(UTC)
    try:
        claimed = await _claim_and_prepare(sessionmaker, now=at, config=config)
    except Exception:
        # A bug here means the claim transaction rolled back (or never
        # committed), so there is nothing DB-side left RUNNING to fail --
        # only report it safely.
        return WorkResult(JobOutcome.FAILED, error_code=_catalog("worker_unexpected_error")[0])
    if claimed is None:
        return WorkResult(JobOutcome.NO_JOB_DUE)
    if isinstance(claimed, WorkResult):
        return claimed

    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(
            sessionmaker,
            job_id=claimed.job_id,
            attempt=claimed.attempt,
            input_revision=claimed.input_revision,
            interval_seconds=heartbeat_interval_seconds,
        )
    )
    try:
        try:
            result = await run_analysis(client, snapshot=claimed.snapshot, config=config)
        except ProviderError as exc:
            return await _finalize_failure(
                sessionmaker,
                job_id=claimed.job_id,
                startup_id=claimed.startup_id,
                attempt=claimed.attempt,
                input_revision=claimed.input_revision,
                error=exc,
                now=datetime.now(UTC),
            )

        return await _finalize_success(
            sessionmaker,
            job_id=claimed.job_id,
            startup_id=claimed.startup_id,
            attempt=claimed.attempt,
            input_revision=claimed.input_revision,
            result=result,
            prompt_version=config.prompt_version,
        )
    except Exception:
        # Anything unforeseen in run_analysis/_finalize_* itself: never leak
        # the exception, and never leave the job stuck RUNNING.
        return await _fail_best_effort(sessionmaker, job_id=claimed.job_id, attempt=claimed.attempt)
    finally:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task


async def recover_stale_running_jobs(
    sessionmaker: SessionFactory, *, now: datetime | None = None
) -> uuid.UUID | None:
    """Recover ONE RUNNING job whose deadline has passed (crashed worker),
    or None if there was nothing to recover. Idempotent and safe to call on
    every poll iteration -- SKIP LOCKED means it never overlaps a live
    attempt or another recovery sweep."""
    at = now or datetime.now(UTC)
    async with sessionmaker() as session, session.begin():
        job = await analysis_repository.claim_stale_running_job(session, now=at)
        if job is None:
            return None
        code, key = _catalog("worker_unexpected_error")
        if job.attempts < job.max_attempts:
            analysis_state.mark_retrying(
                job, next_attempt_at=at, error_code=code, error_message_key=key
            )
        else:
            analysis_state.mark_failed(job, error_code=code, error_message_key=key)
        return job.id


Sleep = Callable[[float], Awaitable[None]]
ShouldContinue = Callable[[], bool]


async def run_worker_loop(
    sessionmaker: SessionFactory,
    *,
    client: ResponsesClient,
    config: WorkerConfig,
    should_continue: ShouldContinue,
    sleep: Sleep,
    poll_interval_seconds: float,
) -> int:
    """Poll until `should_continue()` is false. Returns iterations executed.

    Each iteration first runs one stale-job recovery sweep, then processes at
    most one due job; if neither found anything to do, it sleeps for
    `poll_interval_seconds` before checking `should_continue()` again. Never
    raises on a job's own failure -- only a bug in this loop itself would.
    """
    iterations = 0
    while should_continue():
        iterations += 1
        recovered = await recover_stale_running_jobs(sessionmaker)
        result = await run_one_job(sessionmaker, client=client, config=config)
        if recovered is None and result.outcome is JobOutcome.NO_JOB_DUE:
            await sleep(poll_interval_seconds)
    return iterations
