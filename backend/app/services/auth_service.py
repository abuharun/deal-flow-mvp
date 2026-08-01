"""Invite activation and email verification orchestration (Task B3, slice B).

Transaction contract:
- Every function flushes but never commits: the calling endpoint owns exactly
  one transaction per request and rolls it back on any failure.
- The verification email is sent *before* the caller commits, so a definitive
  provider rejection rolls the user/invite/token/audit rows back together.
  An ambiguous network timeout (sent but unconfirmed) remains a known risk
  until an outbox exists — deliberately out of scope for this slice.

Security contract:
- Raw invite/verification tokens and passwords are never logged, stored, or
  placed in audit metadata or error details.
- Invalid, expired, unknown, and mismatched invites all collapse into one
  safe VALIDATION_FAILED answer so responses leak nothing beyond possession
  of a token.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models import AuditActorType, EmailTokenPurpose, Invite, UiLocale, User, UserRole
from app.security.passwords import hash_password
from app.services.audit_service import write_audit
from app.services.email_service import (
    EmailDeliveryError,
    EmailTransport,
    build_verification_email,
    build_verification_url,
)
from app.services.email_token_service import (
    EmailTokenConsumeOutcome,
    consume_email_token,
    create_email_token,
)
from app.services.invite_service import hash_invite_token

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _invalid_invite() -> ApiError:
    return ApiError(
        422, "VALIDATION_FAILED", "errors.validationFailed", "invite token is invalid or expired"
    )


def _invalid_verification() -> ApiError:
    return ApiError(
        422,
        "VALIDATION_FAILED",
        "errors.validationFailed",
        "verification token is invalid or expired",
    )


async def _lock_invite(session: AsyncSession, token: str) -> Invite | None:
    """Row-lock the invite so concurrent activations serialize on it."""
    try:
        token_hash = hash_invite_token(token)
    except UnicodeEncodeError:
        # Real tokens are always ASCII; anything else can be rejected outright.
        return None
    return (
        await session.execute(
            sa.select(Invite).where(Invite.token_hash == token_hash).with_for_update()
        )
    ).scalar_one_or_none()


async def activate_invite(
    session: AsyncSession,
    *,
    email_transport: EmailTransport,
    frontend_public_url: str,
    token: str,
    email: str,
    password: str,
    full_name: str,
    locale: str,
    clock: Clock = _utcnow,
) -> User:
    """Stage the founder account, consume the invite, and send the verify email.

    Flushes but never commits — the caller owns the transaction boundary.
    """
    now = clock()
    invite = await _lock_invite(session, token)
    if invite is None:
        raise _invalid_invite()
    if invite.used_at is not None:
        raise ApiError(409, "INVITE_USED", "errors.inviteUsed", "invite has already been used")
    if invite.expires_at <= now:
        raise _invalid_invite()
    if invite.email.lower() != email.lower():
        # Same safe answer as an unknown token: possession of a token must not
        # reveal which email it was issued for.
        raise _invalid_invite()

    existing = (
        await session.execute(sa.select(User.id).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise ApiError(
            409, "CONFLICT", "errors.conflict", "an account with this email already exists"
        )

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=UserRole.FOUNDER,
        locale=UiLocale(locale),
    )
    session.add(user)
    await session.flush()

    invite.used_at = now
    grant = await create_email_token(
        session, user_id=user.id, purpose=EmailTokenPurpose.VERIFY, clock=clock
    )
    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        actor_id=user.id,
        action="auth.signup",
        entity_type="user",
        entity_id=user.id,
        metadata={"invite_id": str(invite.id), "locale": locale},
    )

    message = build_verification_email(
        to=email,
        verification_url=build_verification_url(frontend_public_url, grant.token),
        locale=locale,
    )
    # Send before the caller commits: a definitive provider failure rolls the
    # whole signup back. Only status/request-id survive into the safe error.
    try:
        await email_transport.send(message)
    except EmailDeliveryError as exc:
        raise ApiError(
            502,
            "EMAIL_DELIVERY_FAILED",
            "errors.emailDeliveryFailed",
            "verification email could not be sent",
        ) from exc
    return user


async def verify_email(session: AsyncSession, *, token: str, clock: Clock = _utcnow) -> User:
    """Consume a VERIFY token and stamp the owner verified exactly once.

    Flushes but never commits — the caller owns the transaction boundary.
    """
    result = await consume_email_token(
        session, token=token, purpose=EmailTokenPurpose.VERIFY, clock=clock
    )
    if result.outcome in (EmailTokenConsumeOutcome.UNKNOWN, EmailTokenConsumeOutcome.EXPIRED):
        raise _invalid_verification()
    if result.outcome is EmailTokenConsumeOutcome.USED:
        raise ApiError(
            409, "CONFLICT", "errors.conflict", "verification token has already been used"
        )

    user = await session.get(User, result.email_token.user_id, with_for_update=True)
    if user is None or user.deleted_at is not None:
        # A token pointing at a soft-deleted account gets the same safe answer
        # as an unknown token; the raised error rolls the consumption back.
        raise _invalid_verification()
    if user.email_verified_at is None:
        user.email_verified_at = clock()
    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        actor_id=user.id,
        action="auth.email_verified",
        entity_type="user",
        entity_id=user.id,
    )
    await session.flush()
    return user
