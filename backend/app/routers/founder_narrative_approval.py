"""Founder narrative approval (/founder/startups/{id}/narrative/approval).

Product contract: a startup becomes visible to investors only because its
founder said so. POST freezes the exact narrative version named in the body
and moves the startup to its locked, VC-visible state in one transaction; GET
returns what was frozen, verbatim, forever.

The request names a version on purpose. "Approve whatever is current" would
let an autosave from another tab slip text in front of investors that the
founder never read, so the version they are looking at is part of the
mutation and a mismatch is refused with 409 NARRATIVE_VERSION_MISMATCH.

Approval is a mutation, so it demands an exact allowed Origin -- the same
policy the other founder state-changing routes use. GET stays origin-free.

Failure modes, all distinct so a client never has to guess:
- 409 NARRATIVE_NOT_READY: no completed report, or the narrative has never
  been materialized. Approval never seeds one; the founder must have read it.
- 409 NARRATIVE_VERSION_MISMATCH: the named version is not current.
- 409 STARTUP_LOCKED: already frozen (at a different version) or otherwise
  VC-visible. Re-approving the SAME version is idempotent 200 instead, with
  no second approval row and no second audit event.
- 404 NARRATIVE_NOT_APPROVED: GET before any approval exists.
- 404 STARTUP_NOT_FOUND / 403 FORBIDDEN_ROLE / 403 FORBIDDEN_ORIGIN as
  everywhere else; foreign and unknown startups stay indistinguishable.

Nothing here sends anything. Approval makes the startup VC-visible; which
investors see it, and when, is future work -- there is no recipient in this
slice.
"""

from uuid import UUID

from fastapi import APIRouter

from app.deps import SessionDep
from app.errors import ApiError
from app.models import NarrativeApproval, NarrativeVersion, Startup
from app.routers.founder_narrative import _narrative_not_ready
from app.routers.founder_startups import (
    _STATE_CHANGING,
    FounderPrincipal,
    _load_owned_startup,
    _startup_locked_error,
)
from app.schemas.narrative_approval import NarrativeApprovalRequest, NarrativeApprovalResponse
from app.services import narrative_approval_service
from app.services.narrative_approval_service import (
    NarrativeApprovalNotFoundError,
    NarrativeVersionMismatchError,
)
from app.services.narrative_service import NarrativeNotReadyError
from app.services.startup_service import StartupLockedError

router = APIRouter(
    prefix="/founder/startups/{startup_id}/narrative/approval", tags=["founder-narrative-approval"]
)


def _not_approved() -> ApiError:
    return ApiError(
        404,
        "NARRATIVE_NOT_APPROVED",
        "errors.narrativeNotApproved",
        "the narrative has not been approved yet",
    )


def _version_mismatch(exc: NarrativeVersionMismatchError) -> ApiError:
    # Version NUMBERS only -- the founder's own bookkeeping, never any text.
    return ApiError(
        409,
        "NARRATIVE_VERSION_MISMATCH",
        "errors.narrativeVersionMismatch",
        f"narrative version {exc.requested} is not the current version {exc.current}",
    )


def _approval_response(
    startup: Startup, approval: NarrativeApproval, version: NarrativeVersion
) -> NarrativeApprovalResponse:
    return NarrativeApprovalResponse(
        startup_id=approval.startup_id,
        narrative_version_id=approval.narrative_version_id,
        version=version.version,
        content=version.content,
        source=version.source,
        report_id=version.report_id,
        input_revision=version.input_revision,
        approved_by=approval.approved_by,
        approved_at=approval.approved_at,
        status=startup.status,
        vc_visible_at=startup.vc_visible_at,
    )


@router.post("", **_STATE_CHANGING)
async def approve_narrative(
    startup_id: UUID,
    payload: NarrativeApprovalRequest,
    principal: FounderPrincipal,
    session: SessionDep,
) -> NarrativeApprovalResponse:
    try:
        # FOR UPDATE on the startups row serializes concurrent approvals, so
        # the freeze and the VC-visible transition can only happen once.
        startup = await _load_owned_startup(session, startup_id, principal, for_update=True)
        approval, version, _ = await narrative_approval_service.approve_narrative(
            session, startup=startup, actor_id=principal.user_id, version=payload.version
        )
        await session.commit()
    except StartupLockedError:
        await session.rollback()
        raise _startup_locked_error() from None
    except NarrativeNotReadyError:
        await session.rollback()
        raise _narrative_not_ready() from None
    except NarrativeVersionMismatchError as exc:
        await session.rollback()
        raise _version_mismatch(exc) from None
    except Exception:
        await session.rollback()
        raise
    return _approval_response(startup, approval, version)


@router.get("")
async def get_narrative_approval(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> NarrativeApprovalResponse:
    startup = await _load_owned_startup(session, startup_id, principal)
    try:
        approval, version = await narrative_approval_service.get_approval(session, startup=startup)
    except NarrativeApprovalNotFoundError:
        raise _not_approved() from None
    return _approval_response(startup, approval, version)
