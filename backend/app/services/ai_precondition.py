"""Pure precondition check for triggering AI research on a startup.

This module never calls OpenAI, never enqueues a job, and never touches the
database, deck bytes, or a founder's answers — it takes plain values the
caller already gathered and returns canonical missing-reason codes only. It
is the seam the next slice (actually triggering AI analysis) will call
before doing any real work; there is no endpoint for it in this slice.
"""

import enum
from dataclasses import dataclass

from app.models.payment import PAYMENT_STATUS_PAID


class AiPreconditionReason(enum.Enum):
    STARTUP_NOT_SUBMITTED = "startup_not_submitted"
    DECK_MISSING = "deck_missing"
    PAYMENT_NOT_PAID = "payment_not_paid"
    CONSENT_MISSING = "consent_missing"


@dataclass(frozen=True, slots=True)
class AiPreconditionResult:
    eligible: bool
    missing: tuple[AiPreconditionReason, ...]


def evaluate_ai_preconditions(
    *,
    startup_submitted: bool,
    deck_exists: bool,
    payment_status: str | None,
    consent_granted: bool,
) -> AiPreconditionResult:
    """Every prerequisite must hold: submitted, deck present, demo payment
    paid, and current-version AI/privacy consent granted."""
    missing: list[AiPreconditionReason] = []
    if not startup_submitted:
        missing.append(AiPreconditionReason.STARTUP_NOT_SUBMITTED)
    if not deck_exists:
        missing.append(AiPreconditionReason.DECK_MISSING)
    if payment_status != PAYMENT_STATUS_PAID:
        missing.append(AiPreconditionReason.PAYMENT_NOT_PAID)
    if not consent_granted:
        missing.append(AiPreconditionReason.CONSENT_MISSING)
    return AiPreconditionResult(eligible=not missing, missing=tuple(missing))
