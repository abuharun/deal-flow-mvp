"""Founder-only AI/privacy consent endpoints (/founder/startups/{id}/consents).

Access model mirrors the other founder-startup routes: founder bearer
principal (VC gets the canonical 403), founder-scoped SQL lookups (foreign
== unknown == one canonical 404), and an exact allowed Origin on the
mutating route.

Product contract: consent is granted per startup, explicitly, at a specific
text_version. Only the server's CURRENT_AI_PRIVACY_VERSION is accepted;
stale or unknown versions answer the canonical 422 CONSENT_VERSION_INVALID.
Granting again at an already-granted version is idempotent. GET returns a
summary (whether the current version is granted) plus the full grant
history, which the frontend needs to hydrate consent state.
"""

from uuid import UUID

from fastapi import APIRouter, Response, status

from app.deps import SessionDep
from app.errors import ApiError
from app.models.consent import CURRENT_AI_PRIVACY_VERSION
from app.repositories import consent_repository
from app.routers.founder_startups import (
    _STATE_CHANGING,
    FounderPrincipal,
    _load_owned_startup,
    _startup_locked_error,
)
from app.schemas.consent import ConsentGrantRequest, ConsentResponse, ConsentSummaryResponse
from app.services import consent_service
from app.services.consent_service import ConsentVersionInvalidError
from app.services.startup_service import StartupLockedError

router = APIRouter(prefix="/founder/startups/{startup_id}/consents", tags=["founder-consents"])


def _consent_version_invalid_error() -> ApiError:
    return ApiError(
        422,
        "CONSENT_VERSION_INVALID",
        "errors.consentVersionInvalid",
        "requested consent kind/version is not currently supported",
    )


@router.post("", **_STATE_CHANGING)
async def grant_consent(
    startup_id: UUID,
    payload: ConsentGrantRequest,
    response: Response,
    principal: FounderPrincipal,
    session: SessionDep,
) -> ConsentResponse:
    try:
        startup = await _load_owned_startup(session, startup_id, principal, for_update=True)
        consent, created = await consent_service.grant_consent(
            session, startup=startup, kind=payload.kind, text_version=payload.text_version
        )
        await session.commit()
    except StartupLockedError:
        await session.rollback()
        raise _startup_locked_error() from None
    except ConsentVersionInvalidError:
        await session.rollback()
        raise _consent_version_invalid_error() from None
    except Exception:
        await session.rollback()
        raise
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return ConsentResponse.model_validate(consent)


@router.get("")
async def get_consents(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> ConsentSummaryResponse:
    startup = await _load_owned_startup(session, startup_id, principal)
    history = await consent_repository.list_for_startup(session, startup_id=startup.id)
    granted = any(consent.text_version == CURRENT_AI_PRIVACY_VERSION for consent in history)
    return ConsentSummaryResponse(
        current_version=CURRENT_AI_PRIVACY_VERSION,
        granted=granted,
        history=[ConsentResponse.model_validate(consent) for consent in history],
    )
