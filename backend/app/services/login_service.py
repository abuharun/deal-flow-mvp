"""Email/password login orchestration (Task B4, slice B1).

Security contract:
- Unknown, soft-deleted, and wrong-password logins collapse into one generic
  INVALID_CREDENTIALS outcome. The unknown/deleted path burns one Argon2
  verification against a module-constant dummy hash so every failure costs
  one verification and timing does not reveal whether the email exists.
- The raw refresh token exists only inside the returned SessionGrant (whose
  repr hides it); audits carry no submitted email, password, hash, or token.
- Failure outcomes are returned, not raised, so the caller can commit the
  staged auth.login_failed audit before surfacing the 401.

Flushes but never commits: the caller owns the transaction boundary, so the
hash upgrade, session row, and success audit commit (or roll back) together.
"""

import enum
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditActorType, User
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.tokens import ACCESS_TOKEN_TTL, create_access_token
from app.services.audit_service import write_audit
from app.services.session_service import SessionGrant, create_session

Clock = Callable[[], datetime]

ACCESS_TOKEN_EXPIRES_IN = int(ACCESS_TOKEN_TTL.total_seconds())

# A stable, valid hash of a fixed fake password (never a production
# credential) at current parameters, so the unknown-user verification costs
# the same as a real one. The verify result is always discarded; the hash
# must never be logged or written anywhere.
_DUMMY_PASSWORD_HASH = hash_password("bevosita-dummy-login-timing-equalizer")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class LoginOutcome(enum.Enum):
    SUCCESS = "success"
    INVALID_CREDENTIALS = "invalid_credentials"
    EMAIL_UNVERIFIED = "email_unverified"


@dataclass(frozen=True, slots=True)
class LoginSuccess:
    """Everything a successful login hands to the HTTP layer, tokens unloggable."""

    user: User
    access_token: str = field(repr=False)
    expires_in: int
    refresh_grant: SessionGrant


@dataclass(frozen=True, slots=True)
class LoginResult:
    """Typed outcome: failures are values so the caller commits their audit."""

    outcome: LoginOutcome
    success: LoginSuccess | None = None


async def _stage_failure_audit(session: AsyncSession, *, reason: str) -> LoginResult:
    # Actor is SYSTEM with no entity/metadata identifiers: a failed attempt
    # must not record the submitted email (existence oracle) or any secret.
    await write_audit(
        session,
        actor_type=AuditActorType.SYSTEM,
        action="auth.login_failed",
        entity_type="user",
        metadata={"reason": reason},
    )
    outcome = (
        LoginOutcome.EMAIL_UNVERIFIED
        if reason == "email_unverified"
        else LoginOutcome.INVALID_CREDENTIALS
    )
    return LoginResult(outcome=outcome)


async def login(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    jwt_secret: str,
    user_agent: str | None = None,
    clock: Clock = _utcnow,
) -> LoginResult:
    """Verify credentials and stage session + audit rows for one login.

    Case-insensitivity comes from the CITEXT email column, not from Python
    normalization. Flushes but never commits.
    """
    user = (await session.execute(sa.select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or user.deleted_at is not None:
        # Burn one verification against the dummy hash so this branch costs
        # the same as a real password check; the result is discarded.
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return await _stage_failure_audit(session, reason="invalid_credentials")
    if not verify_password(password, user.password_hash):
        return await _stage_failure_audit(session, reason="invalid_credentials")
    if user.email_verified_at is None:
        return await _stage_failure_audit(session, reason="email_unverified")

    if needs_rehash(user.password_hash):
        # Transparent upgrade to current Argon2 parameters; part of the same
        # transaction, so a later failure rolls it back with everything else.
        user.password_hash = hash_password(password)

    grant = await create_session(session, user_id=user.id, user_agent=user_agent, clock=clock)
    access_token = create_access_token(
        user_id=user.id, role=user.role, secret=jwt_secret, clock=clock
    )
    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        actor_id=user.id,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        metadata={"session_family_id": str(grant.auth_session.family_id)},
    )
    await session.flush()
    return LoginResult(
        outcome=LoginOutcome.SUCCESS,
        success=LoginSuccess(
            user=user,
            access_token=access_token,
            expires_in=ACCESS_TOKEN_EXPIRES_IN,
            refresh_grant=grant,
        ),
    )
