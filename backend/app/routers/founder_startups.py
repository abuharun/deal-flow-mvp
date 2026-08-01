"""Founder-only startup + submission endpoints (/founder/startups).

Access model:
- Every route requires a founder bearer principal; a VC token gets the
  canonical 403 FORBIDDEN_ROLE from require_role.
- Every ID lookup is scoped by founder_id in SQL, so a foreign startup and a
  nonexistent one share a single canonical 404 — ownership never leaks.
- State-changing routes additionally demand an exact allowed Origin, the same
  policy the cookie-bound auth routes use.

Each endpoint owns exactly one DB transaction: the service stages rows (and
the audit trail) and flushes; the endpoint commits on success and rolls back
on any failure, so a startup and its submission can never be observed apart.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.deps import Principal, SessionDep, require_allowed_origin, require_role
from app.errors import ApiError
from app.models import UserRole
from app.repositories import startup_repository
from app.schemas.startup import (
    StartupCreateRequest,
    StartupDetailResponse,
    StartupPatchRequest,
    StartupResponse,
    SubmissionPatchRequest,
)
from app.services import startup_service

router = APIRouter(prefix="/founder/startups", tags=["founder-startups"])


def _startup_not_found() -> ApiError:
    # One fixed 404 for unknown AND foreign ids: ownership must never leak
    # through a 403, a different body, or any other distinguishable signal.
    return ApiError(404, "STARTUP_NOT_FOUND", "errors.startupNotFound", "startup not found")


async def _load_owned_startup(
    session: SessionDep,
    startup_id: UUID,
    principal: Principal,
    *,
    with_submission: bool = False,
    for_update: bool = False,
):
    startup = await startup_repository.get_owned_startup(
        session,
        startup_id=startup_id,
        founder_id=principal.user_id,
        with_submission=with_submission,
        for_update=for_update,
    )
    if startup is None:
        raise _startup_not_found()
    return startup


FounderPrincipal = Annotated[Principal, Depends(require_role(UserRole.FOUNDER))]

# Bearer routes that mutate state still verify the caller's web context: a
# browser-held token used from a foreign page must die at the door.
_STATE_CHANGING = {"dependencies": [Depends(require_allowed_origin)]}


@router.post("", status_code=status.HTTP_201_CREATED, **_STATE_CHANGING)
async def create_startup(
    payload: StartupCreateRequest, principal: FounderPrincipal, session: SessionDep
) -> StartupDetailResponse:
    try:
        startup = await startup_service.create_startup(
            session,
            founder_id=principal.user_id,
            name=payload.name,
            one_liner=payload.one_liner,
            sector=payload.sector,
            funding_stage=payload.funding_stage,
            city=payload.city,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return StartupDetailResponse.model_validate(startup)


@router.post("/{startup_id}/submit", **_STATE_CHANGING)
async def submit_startup(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> StartupResponse:
    try:
        startup = await _load_owned_startup(
            session, startup_id, principal, with_submission=True, for_update=True
        )
        await startup_service.submit_startup(session, startup=startup)
        await session.refresh(startup, ("updated_at",))
        await session.commit()
    except startup_service.StartupLockedError:
        await session.rollback()
        raise _startup_locked_error() from None
    except startup_service.StartupAlreadySubmittedError:
        await session.rollback()
        raise ApiError(
            409,
            "STARTUP_ALREADY_SUBMITTED",
            "errors.startupAlreadySubmitted",
            "startup has already been submitted",
        ) from None
    except startup_service.SubmissionIncompleteError as exc:
        await session.rollback()
        # Field NAMES only — never the founder's answers.
        raise ApiError(
            422,
            "SUBMISSION_INCOMPLETE",
            "errors.submissionIncomplete",
            f"missing required answers: {', '.join(exc.missing_fields)}",
        ) from None
    except Exception:
        await session.rollback()
        raise
    return StartupResponse.model_validate(startup)


@router.get("")
async def list_startups(principal: FounderPrincipal, session: SessionDep) -> list[StartupResponse]:
    startups = await startup_repository.list_startups_for_founder(
        session, founder_id=principal.user_id
    )
    return [StartupResponse.model_validate(startup) for startup in startups]


@router.get("/{startup_id}")
async def get_startup(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> StartupDetailResponse:
    startup = await _load_owned_startup(session, startup_id, principal, with_submission=True)
    return StartupDetailResponse.model_validate(startup)


def _startup_locked_error() -> ApiError:
    return ApiError(
        409,
        "STARTUP_LOCKED",
        "errors.startupLocked",
        "startup is visible to investors and can no longer be edited",
    )


@router.patch("/{startup_id}", **_STATE_CHANGING)
async def patch_startup(
    startup_id: UUID,
    payload: StartupPatchRequest,
    principal: FounderPrincipal,
    session: SessionDep,
) -> StartupResponse:
    try:
        startup = await _load_owned_startup(session, startup_id, principal, for_update=True)
        await startup_service.update_startup(session, startup=startup, changes=payload.changes())
        await session.refresh(startup, ("updated_at",))
        await session.commit()
    except startup_service.StartupLockedError:
        await session.rollback()
        raise _startup_locked_error() from None
    except Exception:
        await session.rollback()
        raise
    return StartupResponse.model_validate(startup)


@router.patch("/{startup_id}/submission", **_STATE_CHANGING)
async def patch_submission(
    startup_id: UUID,
    payload: SubmissionPatchRequest,
    principal: FounderPrincipal,
    session: SessionDep,
) -> StartupDetailResponse:
    try:
        # FOR UPDATE on the startups row serializes concurrent autosaves, so
        # input_revision can only move forward by exactly one per transaction.
        startup = await _load_owned_startup(
            session, startup_id, principal, with_submission=True, for_update=True
        )
        await startup_service.update_submission(session, startup=startup, changes=payload.changes())
        await session.refresh(startup, ("updated_at",))
        await session.refresh(startup.submission, ("updated_at",))
        await session.commit()
    except startup_service.StartupLockedError:
        await session.rollback()
        raise _startup_locked_error() from None
    except Exception:
        await session.rollback()
        raise
    return StartupDetailResponse.model_validate(startup)
