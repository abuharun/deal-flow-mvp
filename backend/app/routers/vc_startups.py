"""Read-only investor endpoints (/vc/startups).

Two GETs, no writes anywhere in this router:
- GET /vc/startups -- the founder-approved, VC-visible startups, newest
  approval first, in bounded deterministic pages.
- GET /vc/startups/{id} -- one startup's dossier: the safe profile, the
  frozen narrative version its founder approved, and the immutable cited
  report behind it (minus the AI's raw narrative draft; see app.schemas.vc).

Access model:
- VC role required. A founder bearer token gets the canonical 403
  FORBIDDEN_ROLE from require_role -- including for a startup that founder
  owns, because the role gate runs before any lookup.
- Active/verified is the canonical auth policy already enforced by
  `get_current_principal` (deleted, unverified, or role-drifted accounts die
  as 401 AUTH_SESSION_REVOKED). This router adds no second account rule.
- Every active pilot VC account sees the same startups: no per-investor
  assignment exists in this slice, so no query here is scoped by viewer.
- Unknown, unapproved, and not-yet-visible ids share one canonical 404
  STARTUP_NOT_FOUND -- the same code the founder surface uses. Whether a
  startup exists at all never leaks.
- No Origin is required: these are reads that carry no ambient credential
  and change nothing. Responses are still marked no-store (see
  app.main.sensitive_response_headers_middleware) because they are
  authenticated and commercially sensitive.

Pagination is `limit`/`offset` over a total SQL order of (approved_at DESC,
id DESC), so a page can never skip or repeat a startup. Both are bounded
here, so an out-of-range value is the canonical 422 rather than an unbounded
scan.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.deps import Principal, SessionDep, require_role
from app.errors import ApiError
from app.models import UserRole
from app.schemas.vc import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_OFFSET,
    MAX_PAGE_SIZE,
    VcApprovedNarrative,
    VcReport,
    VcStartupDossierResponse,
    VcStartupListResponse,
    VcStartupSummary,
)
from app.services import vc_access_service
from app.services.vc_access_service import StartupNotVisibleError

router = APIRouter(prefix="/vc/startups", tags=["vc-startups"])

VcPrincipal = Annotated[Principal, Depends(require_role(UserRole.VC))]

Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0, le=MAX_PAGE_OFFSET)]


def _startup_not_found() -> ApiError:
    # Deliberately the founder surface's code and wording: an investor asking
    # about an unapproved, foreign, or nonexistent startup gets one answer.
    return ApiError(404, "STARTUP_NOT_FOUND", "errors.startupNotFound", "startup not found")


@router.get("")
async def list_visible_startups(
    principal: VcPrincipal,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> VcStartupListResponse:
    page = await vc_access_service.list_visible_startups(session, limit=limit, offset=offset)
    return VcStartupListResponse(
        items=[
            VcStartupSummary.from_row(startup, approved_at=approved_at)
            for startup, approved_at in page.rows
        ],
        limit=limit,
        offset=offset,
        total=page.total,
    )


@router.get("/{startup_id}")
async def get_startup_dossier(
    startup_id: UUID, principal: VcPrincipal, session: SessionDep
) -> VcStartupDossierResponse:
    try:
        startup, approval, version, report, sources = await vc_access_service.get_startup_dossier(
            session, startup_id=startup_id
        )
    except StartupNotVisibleError:
        raise _startup_not_found() from None
    return VcStartupDossierResponse(
        startup=VcStartupSummary.from_row(startup, approved_at=approval.approved_at),
        narrative=VcApprovedNarrative.from_rows(approval, version),
        report=VcReport.from_row(report, sources),
    )
