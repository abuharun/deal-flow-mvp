"""Password reset orchestration (Task B5, slice A).

Transaction contract:
- Both functions flush but never commit: the calling endpoint owns exactly
  one transaction per request. `request_password_reset` returns a typed
  outcome so the router can roll back a failed delivery yet still answer the
  same generic 202; `reset_password` raises safe ApiErrors, and the raised
  error rolls the token consumption back with everything else.
- The reset email is sent *before* the caller commits, so a delivery failure
  rolls the RESET token and audit back together and a retry can issue a
  fresh token. An ambiguous network timeout (sent but unconfirmed) remains a
  known residual until an outbox exists — the same deliberate gap as the
  verification flow in auth_service.

Security contract:
- The response never varies by account state: unknown, soft-deleted, and
  unverified emails perform no token/email work and delivery failures are
  swallowed into a typed outcome, so nothing observable becomes an existence
  oracle. Audits never carry the submitted email, a raw token, or a password.
- Known boundary: access JWTs are stateless, so one issued before the reset
  stays cryptographically valid for its remaining <=15 min lifetime. Only
  refresh sessions are revoked here; an access-side invalidation watermark
  is future work for the auth dependencies.
"""

import enum
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models import AuditActorType, EmailTokenPurpose, User
from app.security.passwords import hash_password
from app.services.audit_service import write_audit
from app.services.email_service import (
    EmailTransport,
    build_password_reset_email,
    build_password_reset_url,
)
from app.services.email_token_service import (
    EmailTokenConsumeOutcome,
    consume_email_token,
    create_email_token,
)
from app.services.session_service import revoke_all_user_sessions

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _invalid_reset() -> ApiError:
    return ApiError(
        422, "VALIDATION_FAILED", "errors.validationFailed", "reset token is invalid or expired"
    )


class ForgotPasswordOutcome(enum.Enum):
    RESET_EMAIL_SENT = "reset_email_sent"
    NOT_ELIGIBLE = "not_eligible"
    DELIVERY_FAILED = "delivery_failed"


@dataclass(frozen=True, slots=True)
class ForgotPasswordResult:
    """Typed outcome so the router can pick commit vs rollback, never the status."""

    outcome: ForgotPasswordOutcome


async def request_password_reset(
    session: AsyncSession,
    *,
    email_transport: EmailTransport,
    frontend_public_url: str,
    email: str,
    clock: Clock = _utcnow,
) -> ForgotPasswordResult:
    """Stage a newest-only RESET token + audit and send the localized email.

    Flushes but never commits. NOT_ELIGIBLE stages nothing at all (no audit:
    any row tied to the submitted email would leak account existence into the
    trail); DELIVERY_FAILED tells the caller to roll the staged rows back.
    """
    user = (await session.execute(sa.select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or user.deleted_at is not None or user.email_verified_at is None:
        return ForgotPasswordResult(outcome=ForgotPasswordOutcome.NOT_ELIGIBLE)

    grant = await create_email_token(
        session, user_id=user.id, purpose=EmailTokenPurpose.RESET, clock=clock
    )
    await write_audit(
        session,
        actor_type=AuditActorType.SYSTEM,
        action="auth.password_reset_requested",
        entity_type="user",
        entity_id=user.id,
    )
    message = build_password_reset_email(
        to=user.email,
        reset_url=build_password_reset_url(frontend_public_url, grant.token),
        locale=user.locale.value,
    )
    try:
        await email_transport.send(message)
    except Exception:  # noqa: BLE001 - any send failure must stay a 202, never an oracle
        return ForgotPasswordResult(outcome=ForgotPasswordOutcome.DELIVERY_FAILED)
    return ForgotPasswordResult(outcome=ForgotPasswordOutcome.RESET_EMAIL_SENT)


async def reset_password(
    session: AsyncSession,
    *,
    token: str,
    new_password: str,
    clock: Clock = _utcnow,
) -> User:
    """Consume a RESET token, store a fresh hash, and revoke every session.

    Flushes but never commits — the caller owns the transaction boundary, so
    the hash, token consumption, revocations, and audit land (or roll back)
    together.
    """
    result = await consume_email_token(
        session, token=token, purpose=EmailTokenPurpose.RESET, clock=clock
    )
    if result.outcome in (EmailTokenConsumeOutcome.UNKNOWN, EmailTokenConsumeOutcome.EXPIRED):
        raise _invalid_reset()
    if result.outcome is EmailTokenConsumeOutcome.USED:
        raise ApiError(409, "CONFLICT", "errors.conflict", "reset token has already been used")

    user = await session.get(User, result.email_token.user_id, with_for_update=True)
    if user is None or user.deleted_at is not None or user.email_verified_at is None:
        # Same safe answer as an unknown token; the raised error rolls the
        # consumption back.
        raise _invalid_reset()

    user.password_hash = hash_password(new_password)
    await revoke_all_user_sessions(session, user_id=user.id, clock=clock)
    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        actor_id=user.id,
        action="auth.password_reset_completed",
        entity_type="user",
        entity_id=user.id,
    )
    await session.flush()
    return user
