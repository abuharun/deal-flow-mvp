"""Email verification/reset tokens: generation, hashed storage, consumption.

Security contract:
- Raw tokens are returned to the caller exactly once and never persisted or
  logged; the database holds only the SHA-256 digest.
- Verification is constant-time and never raises on malformed input.
- Issuing a new token marks any still-active token for the same user/purpose
  as used in the same transaction, so only the newest token is usable.

Flushes but never commits: the caller owns the transaction boundary.
"""

import enum
import hashlib
import hmac
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmailToken, EmailTokenPurpose

# 32 bytes = 256 bits of entropy; token_urlsafe emits unpadded url-safe base64.
_TOKEN_BYTES = 32
DEFAULT_VERIFY_TTL = timedelta(hours=24)
DEFAULT_RESET_TTL = timedelta(minutes=30)
_DEFAULT_TTLS = {
    EmailTokenPurpose.VERIFY: DEFAULT_VERIFY_TTL,
    EmailTokenPurpose.RESET: DEFAULT_RESET_TTL,
}

Clock = Callable[[], datetime]
TokenFactory = Callable[[], str]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def generate_email_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_email_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def verify_email_token(token: str, token_hash: bytes) -> bool:
    try:
        candidate = hash_email_token(token)
    except UnicodeEncodeError:
        # Real tokens are always ASCII; anything else can be rejected outright.
        return False
    return hmac.compare_digest(candidate, token_hash)


@dataclass(frozen=True, slots=True)
class EmailTokenGrant:
    """The one-time handoff of a freshly created email token to its caller."""

    email_token: EmailToken
    token: str


class EmailTokenConsumeOutcome(enum.Enum):
    CONSUMED = "consumed"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    USED = "used"


@dataclass(frozen=True, slots=True)
class EmailTokenConsumption:
    """Typed outcome of a consume attempt; the row is returned only on success."""

    outcome: EmailTokenConsumeOutcome
    email_token: EmailToken | None = None


async def create_email_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    purpose: EmailTokenPurpose,
    clock: Clock = _utcnow,
    token_factory: TokenFactory = generate_email_token,
    expires_in: timedelta | None = None,
) -> EmailTokenGrant:
    """Persist a hashed token and return the raw token exactly once.

    Any still-active token for the same user/purpose is marked used in the
    same transaction, so at most one token per user/purpose is ever live.
    """
    now = clock()
    await session.execute(
        sa.update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
            EmailToken.expires_at > now,
        )
        .values(used_at=now)
    )
    token = token_factory()
    email_token = EmailToken(
        user_id=user_id,
        purpose=purpose,
        token_hash=hash_email_token(token),
        expires_at=now + (expires_in if expires_in is not None else _DEFAULT_TTLS[purpose]),
    )
    session.add(email_token)
    await session.flush()
    return EmailTokenGrant(email_token=email_token, token=token)


async def consume_email_token(
    session: AsyncSession,
    *,
    token: str,
    purpose: EmailTokenPurpose,
    clock: Clock = _utcnow,
) -> EmailTokenConsumption:
    """Atomically mark a token used, locking its row against concurrent consumers."""
    try:
        token_hash = hash_email_token(token)
    except UnicodeEncodeError:
        return EmailTokenConsumption(outcome=EmailTokenConsumeOutcome.UNKNOWN)
    row = (
        await session.execute(
            sa.select(EmailToken)
            .where(EmailToken.token_hash == token_hash, EmailToken.purpose == purpose)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return EmailTokenConsumption(outcome=EmailTokenConsumeOutcome.UNKNOWN)
    if row.used_at is not None:
        return EmailTokenConsumption(outcome=EmailTokenConsumeOutcome.USED)
    if row.expires_at <= clock():
        return EmailTokenConsumption(outcome=EmailTokenConsumeOutcome.EXPIRED)
    row.used_at = clock()
    await session.flush()
    return EmailTokenConsumption(outcome=EmailTokenConsumeOutcome.CONSUMED, email_token=row)
