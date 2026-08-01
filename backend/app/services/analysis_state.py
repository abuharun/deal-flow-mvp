"""State-machine helpers for the future AI-analysis worker.

No worker loop and no provider calls live here: this module only encodes
the LEGAL transitions an analysis_jobs row may make. Callers must already
hold the row lock (via `analysis_repository.get_for_update`) before calling
any of these; each function then validates the job's CURRENT status against
a fixed transition table and refuses (never silently no-ops) anything
illegal. A terminal job (completed/failed) can never transition again.

Every completion/failure write is validated through the
AnalysisCompletionInput/AnalysisFailureInput schemas before it ever touches
the row, so a bad token count, an over-budget cost estimate, or an unsafe
error code/key is rejected before the DB CHECK backstop is reached.
"""

from datetime import datetime

from sqlalchemy import func

from app.models.analysis_job import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RETRYING,
    STATUS_RUNNING,
    TERMINAL_STATUSES,
    AnalysisJob,
)
from app.schemas.analysis import AnalysisCompletionInput, AnalysisFailureInput

_LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_QUEUED: frozenset({STATUS_RUNNING}),
    STATUS_RUNNING: frozenset({STATUS_RETRYING, STATUS_COMPLETED, STATUS_FAILED}),
    STATUS_RETRYING: frozenset({STATUS_RUNNING, STATUS_FAILED}),
    STATUS_COMPLETED: frozenset(),
    STATUS_FAILED: frozenset(),
}


class IllegalTransitionError(Exception):
    """The requested status change is not a legal edge from the current one."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot transition analysis job from {current!r} to {target!r}")
        self.current = current
        self.target = target


class TerminalStateError(IllegalTransitionError):
    """The job already reached completed/failed; terminal state is immutable."""


class MaxAttemptsExceededError(Exception):
    """The job has already used every attempt max_attempts allows."""


def _require_legal(job: AnalysisJob, target: str) -> None:
    if job.status in TERMINAL_STATUSES:
        raise TerminalStateError(job.status, target)
    if target not in _LEGAL_TRANSITIONS.get(job.status, frozenset()):
        raise IllegalTransitionError(job.status, target)


def start_running(job: AnalysisJob, *, deadline_at: datetime | None = None) -> AnalysisJob:
    """queued->running or retrying->running: begin (or resume) one attempt."""
    _require_legal(job, STATUS_RUNNING)
    if job.attempts >= job.max_attempts:
        raise MaxAttemptsExceededError
    if job.started_at is None:
        job.started_at = func.now()
    job.status = STATUS_RUNNING
    job.attempts += 1
    job.heartbeat_at = func.now()
    job.next_attempt_at = None
    if deadline_at is not None:
        job.deadline_at = deadline_at
    return job


def mark_retrying(
    job: AnalysisJob, *, next_attempt_at: datetime, error_code: str, error_message_key: str
) -> AnalysisJob:
    """running->retrying: this attempt failed but another one remains."""
    _require_legal(job, STATUS_RETRYING)
    failure = AnalysisFailureInput(error_code=error_code, error_message_key=error_message_key)
    job.status = STATUS_RETRYING
    job.next_attempt_at = next_attempt_at
    job.last_error_code = failure.error_code
    job.last_error_message_key = failure.error_message_key
    return job


def mark_completed(
    job: AnalysisJob, *, completion: AnalysisCompletionInput | None = None
) -> AnalysisJob:
    """running->completed: the attempt succeeded."""
    _require_legal(job, STATUS_COMPLETED)
    completion = completion if completion is not None else AnalysisCompletionInput()
    job.status = STATUS_COMPLETED
    job.finished_at = func.now()
    job.next_attempt_at = None
    job.model = completion.model
    job.prompt_version = completion.prompt_version
    job.input_tokens = completion.input_tokens
    job.output_tokens = completion.output_tokens
    job.cost_estimate_usd = completion.cost_estimate_usd
    return job


def mark_failed(job: AnalysisJob, *, error_code: str, error_message_key: str) -> AnalysisJob:
    """running->failed or retrying->failed: every attempt is exhausted."""
    _require_legal(job, STATUS_FAILED)
    failure = AnalysisFailureInput(error_code=error_code, error_message_key=error_message_key)
    job.status = STATUS_FAILED
    job.finished_at = func.now()
    job.next_attempt_at = None
    job.last_error_code = failure.error_code
    job.last_error_message_key = failure.error_message_key
    return job
