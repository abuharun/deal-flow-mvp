"""Founder-only demo payment endpoint (/founder/startups/{id}/payment).

Access model mirrors the other founder-startup routes: founder bearer
principal (VC gets the canonical 403), founder-scoped SQL lookups (foreign
== unknown == one canonical 404), and an exact allowed Origin on the
mutating route.

Product contract: this is an honest demo/stub, never a real payment
gateway. The founder explicitly chooses a simulated outcome; nothing in the
response or its copy may ever imply a real charge occurred. A successful
('paid') payment can never regress to 'failed' — that attempt answers a
canonical 409, not a silent no-op or overwrite.
"""

from uuid import UUID

from fastapi import APIRouter, Response, status

from app.deps import SessionDep
from app.errors import ApiError
from app.routers.founder_startups import (
    _STATE_CHANGING,
    FounderPrincipal,
    _load_owned_startup,
    _startup_locked_error,
)
from app.schemas.payment import PaymentResponse, PaymentSimulateRequest
from app.services import payment_service
from app.services.payment_service import PaymentAlreadyPaidError
from app.services.startup_service import StartupLockedError

router = APIRouter(prefix="/founder/startups/{startup_id}/payment", tags=["founder-payment"])


def _payment_not_found() -> ApiError:
    return ApiError(404, "PAYMENT_NOT_FOUND", "errors.paymentNotFound", "no demo payment on record")


def _payment_already_paid_error() -> ApiError:
    return ApiError(
        409,
        "PAYMENT_ALREADY_PAID",
        "errors.paymentAlreadyPaid",
        "a successful demo payment already exists and cannot be reverted",
    )


@router.post("", **_STATE_CHANGING)
async def submit_payment(
    startup_id: UUID,
    payload: PaymentSimulateRequest,
    response: Response,
    principal: FounderPrincipal,
    session: SessionDep,
) -> PaymentResponse:
    try:
        startup = await _load_owned_startup(session, startup_id, principal, for_update=True)
        payment, created = await payment_service.submit_payment(
            session, startup=startup, simulate_outcome=payload.simulate_outcome
        )
        await session.commit()
    except StartupLockedError:
        await session.rollback()
        raise _startup_locked_error() from None
    except PaymentAlreadyPaidError:
        await session.rollback()
        raise _payment_already_paid_error() from None
    except Exception:
        await session.rollback()
        raise
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return PaymentResponse.model_validate(payment)


@router.get("")
async def get_payment(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> PaymentResponse:
    startup = await _load_owned_startup(session, startup_id, principal)
    payment = await payment_service.get_payment(session, startup=startup)
    if payment is None:
        raise _payment_not_found()
    return PaymentResponse.model_validate(payment)
