"""Refresh-token sessions: hashed storage, rotation families, reuse detection.

Security contract:
- Raw refresh tokens are returned to the caller exactly once, inside a frozen
  grant whose repr hides them; the database holds only the SHA-256 digest and
  nothing here ever logs or raises token material.
- Verification is constant-time and never raises on malformed input.
- A family shares one absolute expiry (30 days from creation); rotation
  inserts a sibling with the SAME expires_at — never an extension.
- Rotation locks the presented row (SELECT FOR UPDATE) so concurrent
  presentations of one token serialize: exactly one caller wins ROTATED, the
  next sees rotated_at set and gets REUSE, which atomically revokes every
  non-revoked row in the family — including the winner's fresh child.
- Outcome precedence: UNKNOWN, then REVOKED, then REUSE, then EXPIRED, then
  ROTATED. Reuse detection outranks expiry (a replayed token is a breach
  signal even past its lifetime); an expired-but-active token is reported
  EXPIRED without mutating any row.

Flushes but never commits: the caller owns the transaction boundary.
"""

import enum
import hashlib
import hmac
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthSession

# 32 bytes = 256 bits of entropy; token_urlsafe emits unpadded url-safe base64.
_TOKEN_BYTES = 32
REFRESH_SESSION_TTL = timedelta(days=30)
USER_AGENT_MAX_LENGTH = 512

Clock = Callable[[], datetime]
TokenFactory = Callable[[], str]
FamilyFactory = Callable[[], uuid.UUID]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_refresh_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def verify_refresh_token(token: str, token_hash: bytes) -> bool:
    try:
        candidate = hash_refresh_token(token)
    except UnicodeEncodeError:
        # Real tokens are always ASCII; anything else can be rejected outright.
        return False
    return hmac.compare_digest(candidate, token_hash)


@dataclass(frozen=True, slots=True)
class SessionGrant:
    """The one-time handoff of a fresh refresh token to its caller."""

    auth_session: AuthSession
    token: str = field(repr=False)


class RotateOutcome(enum.Enum):
    ROTATED = "rotated"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    REVOKED = "revoked"
    REUSE = "reuse"


@dataclass(frozen=True, slots=True)
class SessionIdentity:
    """Token-free identity of a resolved session row, safe for audits."""

    session_id: uuid.UUID
    user_id: uuid.UUID
    family_id: uuid.UUID
    expires_at: datetime


def _identity_of(row: AuthSession) -> SessionIdentity:
    return SessionIdentity(
        session_id=row.id,
        user_id=row.user_id,
        family_id=row.family_id,
        expires_at=row.expires_at,
    )


@dataclass(frozen=True, slots=True)
class SessionRotation:
    """Typed outcome of a rotation attempt; a grant is issued only on ROTATED.

    `identity` describes the presented row whenever one exists (every outcome
    but UNKNOWN), so callers can audit reuse by family without the raw token.
    """

    outcome: RotateOutcome
    grant: SessionGrant | None = None
    identity: SessionIdentity | None = None


@dataclass(frozen=True, slots=True)
class SessionRevocation:
    """Result of resolving a raw token and revoking its whole family."""

    identity: SessionIdentity
    newly_revoked: int


def _truncate_user_agent(user_agent: str | None) -> str | None:
    if user_agent is None:
        return None
    return user_agent[:USER_AGENT_MAX_LENGTH]


async def create_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    user_agent: str | None = None,
    clock: Clock = _utcnow,
    token_factory: TokenFactory = generate_refresh_token,
    family_factory: FamilyFactory = uuid.uuid4,
) -> SessionGrant:
    """Open a new session family and return the raw token exactly once.

    The family's absolute expiry is fixed here at now + 30 days; every later
    rotation inherits it unchanged.
    """
    now = clock()
    token = token_factory()
    auth_session = AuthSession(
        user_id=user_id,
        family_id=family_factory(),
        token_hash=hash_refresh_token(token),
        expires_at=now + REFRESH_SESSION_TTL,
        user_agent=_truncate_user_agent(user_agent),
    )
    session.add(auth_session)
    await session.flush()
    return SessionGrant(auth_session=auth_session, token=token)


async def rotate_session(
    session: AsyncSession,
    *,
    token: str,
    clock: Clock = _utcnow,
    token_factory: TokenFactory = generate_refresh_token,
) -> SessionRotation:
    """Exchange a refresh token for a successor, locking its row against races."""
    try:
        token_hash = hash_refresh_token(token)
    except UnicodeEncodeError:
        return SessionRotation(outcome=RotateOutcome.UNKNOWN)
    row = (
        await session.execute(
            sa.select(AuthSession).where(AuthSession.token_hash == token_hash).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return SessionRotation(outcome=RotateOutcome.UNKNOWN)
    identity = _identity_of(row)
    now = clock()
    if row.revoked_at is not None:
        return SessionRotation(outcome=RotateOutcome.REVOKED, identity=identity)
    if row.rotated_at is not None:
        # Replay of an already-rotated token: treat the family as stolen.
        await session.execute(
            sa.update(AuthSession)
            .where(AuthSession.family_id == row.family_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await session.flush()
        return SessionRotation(outcome=RotateOutcome.REUSE, identity=identity)
    if row.expires_at <= now:
        return SessionRotation(outcome=RotateOutcome.EXPIRED, identity=identity)

    row.rotated_at = now
    new_token = token_factory()
    child = AuthSession(
        user_id=row.user_id,
        family_id=row.family_id,
        token_hash=hash_refresh_token(new_token),
        # Absolute family expiry: the child inherits it verbatim.
        expires_at=row.expires_at,
        user_agent=row.user_agent,
    )
    session.add(child)
    await session.flush()
    return SessionRotation(
        outcome=RotateOutcome.ROTATED,
        grant=SessionGrant(auth_session=child, token=new_token),
        identity=identity,
    )


async def revoke_family_by_token(
    session: AsyncSession,
    *,
    token: str,
    clock: Clock = _utcnow,
) -> SessionRevocation | None:
    """Resolve a raw token under lock and revoke its entire family (logout).

    Any known row — active, rotated, expired, or already revoked — resolves;
    unknown or malformed tokens return None. `newly_revoked` counts the rows
    this call actually stamped (0 means the family was already dead), so the
    caller can audit real logouts without re-revealing state. Flushes but
    never commits.
    """
    try:
        token_hash = hash_refresh_token(token)
    except UnicodeEncodeError:
        return None
    row = (
        await session.execute(
            sa.select(AuthSession).where(AuthSession.token_hash == token_hash).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    newly_revoked = await revoke_session_family(session, family_id=row.family_id, clock=clock)
    return SessionRevocation(identity=_identity_of(row), newly_revoked=newly_revoked)


async def revoke_session_family(
    session: AsyncSession,
    *,
    family_id: uuid.UUID,
    clock: Clock = _utcnow,
) -> int:
    """Revoke every still-active row in one family; returns how many were stamped."""
    result = await session.execute(
        sa.update(AuthSession)
        .where(AuthSession.family_id == family_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=clock())
    )
    await session.flush()
    return result.rowcount


async def revoke_all_user_sessions(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    clock: Clock = _utcnow,
) -> int:
    """Revoke every still-active session of a user, across all families."""
    result = await session.execute(
        sa.update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=clock())
    )
    await session.flush()
    return result.rowcount
