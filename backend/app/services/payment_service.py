"""Founder demo/pilot payment lifecycle: per-startup, honest, non-regressing.

Transaction contract (same as the other services): every function stages
rows and flushes but never commits — the endpoint owns the boundary.

Product contract: this is an honest demo/stub, never a real gateway. The
founder explicitly picks a simulated outcome; nothing here ever calls out to
a payment processor. A successful ('paid') payment can never regress to
'failed' — a later 'failed' simulation on an already-paid startup is refused
outright, never silently ignored or overwritten.

Audit hygiene: metadata carries only IDs, mode, and status — never an
amount or any value that could be mistaken for a real financial claim.
"""

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditActorType, Payment, Startup
from app.models.payment import PAYMENT_STATUS_FAILED, PAYMENT_STATUS_PAID
from app.repositories import payment_repository
from app.services.audit_service import write_audit
from app.services.startup_service import StartupLockedError, is_locked


class PaymentAlreadyPaidError(Exception):
    """A successful demo payment exists; it cannot be reverted to failed."""


def ensure_payment_mutable(startup: Startup) -> None:
    """Refuse payment mutations once the startup is VC-visible."""
    if is_locked(startup):
        raise StartupLockedError


async def _audit(session: AsyncSession, startup: Startup, action: str, payment: Payment) -> None:
    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        actor_id=startup.founder_id,
        action=action,
        entity_type="startup",
        entity_id=startup.id,
        metadata={
            "status": startup.status.value,
            "payment_id": str(payment.id),
            "payment_mode": payment.mode,
            "payment_status": payment.status,
        },
    )


def _action_for(status: str) -> str:
    return (
        "startup.payment_simulated_paid"
        if status == PAYMENT_STATUS_PAID
        else "startup.payment_simulated_failed"
    )


async def get_payment(session: AsyncSession, *, startup: Startup) -> Payment | None:
    """Current payment row, or None if the founder has never simulated one."""
    return await payment_repository.get_for_startup(session, startup_id=startup.id)


async def submit_payment(
    session: AsyncSession, *, startup: Startup, simulate_outcome: str
) -> tuple[Payment, bool]:
    """Record the founder's chosen simulated outcome.

    Returns (payment, created). `created` is True only the first time this
    startup ever gets a payment row; every later call (idempotent repeat,
    failed->paid retry) returns False, even when the row's status changes.
    """
    ensure_payment_mutable(startup)
    existing = await payment_repository.get_for_startup(session, startup_id=startup.id)

    if existing is None:
        payment = Payment(
            startup_id=startup.id,
            status=simulate_outcome,
            paid_at=func.now() if simulate_outcome == PAYMENT_STATUS_PAID else None,
        )
        session.add(payment)
        await session.flush()
        await session.refresh(payment)
        await _audit(session, startup, _action_for(simulate_outcome), payment)
        return payment, True

    if existing.status == PAYMENT_STATUS_PAID:
        if simulate_outcome == PAYMENT_STATUS_PAID:
            return existing, False
        raise PaymentAlreadyPaidError

    # existing.status == PAYMENT_STATUS_FAILED
    if simulate_outcome == PAYMENT_STATUS_FAILED:
        return existing, False

    existing.status = PAYMENT_STATUS_PAID
    existing.paid_at = func.now()
    await session.flush()
    await session.refresh(existing, ("paid_at", "updated_at"))
    await _audit(session, startup, _action_for(PAYMENT_STATUS_PAID), existing)
    return existing, False
