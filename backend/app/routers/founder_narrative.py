"""Founder-only pitch-narrative endpoints (/founder/startups/{id}/narrative).

MVP product contract: ONE free-text narrative per startup, in whatever
language the founder chooses -- no route here takes a locale, and the UZ/RU
UI language never splits the text. The narrative is seeded from the
immutable report's `pitch_narrative_draft` the first time the founder reads
it, and every save that changes the text appends a new immutable version;
the report itself is never touched by anything in this module.

Access model mirrors the other founder-startup routes: founder bearer
principal (VC gets the canonical 403 FORBIDDEN_ROLE), a founder-scoped SQL
lookup (foreign == unknown == one canonical 404 STARTUP_NOT_FOUND), the
canonical 409 STARTUP_LOCKED once the startup is VC-visible, and an exact
allowed Origin on the mutating route only.

Two narrative-specific failures, both deliberately distinct from
STARTUP_NOT_FOUND so a caller can tell them apart without either leaking
ownership: 409 NARRATIVE_NOT_READY (the startup has no completed report to
seed from yet) and 404 NARRATIVE_VERSION_NOT_FOUND (this startup's history
has no such version).

Every read materializes the seed if it is missing, which is a write, so each
handler owns one transaction: the seed happens under the startup's row lock
and commits before anything is rendered, or rolls back entirely.
"""

from uuid import UUID

from fastapi import APIRouter, Path

from app.deps import SessionDep
from app.errors import ApiError
from app.models import NarrativeVersion, StartupNarrative
from app.routers.founder_startups import (
    _STATE_CHANGING,
    FounderPrincipal,
    _load_owned_startup,
    _startup_locked_error,
)
from app.schemas.narrative import (
    NarrativeCurrentResponse,
    NarrativePatchRequest,
    NarrativeVersionListResponse,
    NarrativeVersionResponse,
    NarrativeVersionSummary,
)
from app.services import narrative_service
from app.services.narrative_service import (
    NarrativeNotReadyError,
    NarrativeVersionNotFoundError,
)
from app.services.startup_service import StartupLockedError

router = APIRouter(prefix="/founder/startups/{startup_id}/narrative", tags=["founder-narrative"])


def _narrative_not_ready() -> ApiError:
    return ApiError(
        409,
        "NARRATIVE_NOT_READY",
        "errors.narrativeNotReady",
        "the AI report that seeds the narrative is not available yet",
    )


def _narrative_version_not_found() -> ApiError:
    return ApiError(
        404,
        "NARRATIVE_VERSION_NOT_FOUND",
        "errors.narrativeVersionNotFound",
        "no such narrative version",
    )


def _current_response(
    current: StartupNarrative, version: NarrativeVersion
) -> NarrativeCurrentResponse:
    return NarrativeCurrentResponse(
        startup_id=version.startup_id,
        version=version.version,
        content=version.content,
        source=version.source,
        report_id=version.report_id,
        input_revision=version.input_revision,
        created_at=version.created_at,
        updated_at=current.updated_at,
    )


async def _seeded_startup(session: SessionDep, startup_id: UUID, principal: FounderPrincipal):
    """The founder's startup, guaranteed to have a materialized narrative.

    The common read path stays lock-free: only when nothing exists yet is the
    startup re-loaded FOR UPDATE, so two concurrent first reads serialize and
    the second one finds the first's version 1 instead of inserting its own.
    """
    startup = await _load_owned_startup(session, startup_id, principal)
    if await narrative_service.get_current(session, startup=startup) is not None:
        return startup
    try:
        startup = await _load_owned_startup(session, startup_id, principal, for_update=True)
        await narrative_service.seed_from_report(
            session, startup=startup, actor_id=principal.user_id
        )
        await session.commit()
    except NarrativeNotReadyError:
        await session.rollback()
        raise _narrative_not_ready() from None
    except Exception:
        await session.rollback()
        raise
    return startup


@router.get("")
async def get_narrative(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> NarrativeCurrentResponse:
    startup = await _seeded_startup(session, startup_id, principal)
    narrative = await narrative_service.get_current(session, startup=startup)
    if narrative is None:  # pragma: no cover - the seed above guarantees one
        raise _narrative_not_ready()
    return _current_response(*narrative)


@router.patch("", **_STATE_CHANGING)
async def save_narrative(
    startup_id: UUID,
    payload: NarrativePatchRequest,
    principal: FounderPrincipal,
    session: SessionDep,
) -> NarrativeCurrentResponse:
    try:
        # FOR UPDATE on the startups row serializes concurrent saves, so the
        # next version number can only be handed out once per transaction.
        startup = await _load_owned_startup(session, startup_id, principal, for_update=True)
        current, version, _ = await narrative_service.save_narrative(
            session, startup=startup, actor_id=principal.user_id, content=payload.content
        )
        await session.commit()
    except StartupLockedError:
        await session.rollback()
        raise _startup_locked_error() from None
    except NarrativeNotReadyError:
        await session.rollback()
        raise _narrative_not_ready() from None
    except Exception:
        await session.rollback()
        raise
    return _current_response(current, version)


@router.get("/versions")
async def list_narrative_versions(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> NarrativeVersionListResponse:
    startup = await _seeded_startup(session, startup_id, principal)
    try:
        current, summaries = await narrative_service.list_versions(session, startup=startup)
    except NarrativeNotReadyError:  # pragma: no cover - the seed guarantees one
        raise _narrative_not_ready() from None
    return NarrativeVersionListResponse(
        current_version=current.current_version,
        versions=[NarrativeVersionSummary.model_validate(row) for row in summaries],
    )


@router.get("/versions/{version}")
async def get_narrative_version(
    startup_id: UUID,
    principal: FounderPrincipal,
    session: SessionDep,
    version: int = Path(ge=1),
) -> NarrativeVersionResponse:
    startup = await _seeded_startup(session, startup_id, principal)
    try:
        row = await narrative_service.get_version(session, startup=startup, version=version)
    except NarrativeVersionNotFoundError:
        raise _narrative_version_not_found() from None
    return NarrativeVersionResponse.model_validate(row)
