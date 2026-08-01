"""Founder-only AI-analysis endpoints (/founder/startups/{startup_id}/analysis).

Access model mirrors the other founder-startup routes: founder bearer
principal (VC gets the canonical 403), founder-scoped SQL lookups (foreign
== unknown == one canonical 404), and an exact allowed Origin on the
triggering route -- checked as a route dependency, before a single DB
mutation happens.

Product contract: the founder explicitly triggers one research run per
startup. Every prerequisite (submitted, deck, demo payment paid, current
consent) must hold; a missing one answers the canonical 422
ANALYSIS_PRECONDITION with a bounded, deterministic list of reason codes
only -- never another startup's state or any private value. Once a job
exists, repeated triggers are idempotent: same job, same 202, no new audit
row. GET reports safe status metadata plus `stale`; a missing job answers
the canonical 404 ANALYSIS_NOT_FOUND. This router never calls OpenAI and
never reads deck bytes.
"""

from uuid import UUID

from fastapi import APIRouter, status

from app.deps import SessionDep
from app.errors import ApiError
from app.models.analysis_job import AnalysisJob
from app.routers.founder_startups import (
    _STATE_CHANGING,
    FounderPrincipal,
    _load_owned_startup,
    _startup_locked_error,
)
from app.schemas.analysis import AnalysisJobResponse, AnalysisTriggerRequest
from app.services import analysis_service
from app.services.analysis_service import AnalysisNotFoundError, AnalysisPreconditionError
from app.services.startup_service import StartupLockedError

router = APIRouter(prefix="/founder/startups/{startup_id}/analysis", tags=["founder-analysis"])


def _analysis_not_found() -> ApiError:
    return ApiError(
        404, "ANALYSIS_NOT_FOUND", "errors.analysisNotFound", "no analysis job on record"
    )


def _analysis_precondition_error(exc: AnalysisPreconditionError) -> ApiError:
    # Reason codes only, in the evaluator's deterministic order -- never
    # another startup's state or a private value.
    reasons = ", ".join(reason.value for reason in exc.missing)
    return ApiError(
        422,
        "ANALYSIS_PRECONDITION",
        "errors.analysisPrecondition",
        f"missing prerequisites: {reasons}",
    )


def _to_response(job: AnalysisJob, *, stale: bool) -> AnalysisJobResponse:
    return AnalysisJobResponse(
        id=job.id,
        startup_id=job.startup_id,
        input_revision=job.input_revision,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        next_attempt_at=job.next_attempt_at,
        last_error_code=job.last_error_code,
        last_error_message_key=job.last_error_message_key,
        stale=stale,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED, **_STATE_CHANGING)
async def trigger_analysis(
    startup_id: UUID,
    principal: FounderPrincipal,
    session: SessionDep,
    payload: AnalysisTriggerRequest | None = None,
) -> AnalysisJobResponse:
    try:
        # FOR UPDATE serializes concurrent triggers for one startup so at
        # most one job row is ever created (the UNIQUE constraint backstops
        # this at the DB level too).
        startup = await _load_owned_startup(session, startup_id, principal, for_update=True)
        job, _created = await analysis_service.trigger_analysis(session, startup=startup)
        await session.commit()
    except StartupLockedError:
        await session.rollback()
        raise _startup_locked_error() from None
    except AnalysisPreconditionError as exc:
        await session.rollback()
        raise _analysis_precondition_error(exc) from None
    except Exception:
        await session.rollback()
        raise
    return _to_response(job, stale=job.input_revision != startup.input_revision)


@router.get("")
async def get_analysis(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> AnalysisJobResponse:
    startup = await _load_owned_startup(session, startup_id, principal)
    try:
        job, stale = await analysis_service.get_analysis_status(session, startup=startup)
    except AnalysisNotFoundError:
        raise _analysis_not_found() from None
    return _to_response(job, stale=stale)
