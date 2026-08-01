"""Invite tokens: generation, hashed storage, verification, activation URLs.

Security contract:
- Raw tokens are returned to the caller exactly once and never persisted or
  logged; the database holds only the SHA-256 digest.
- Verification is constant-time and never raises on malformed input.
"""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Invite

# 32 bytes = 256 bits of entropy; token_urlsafe emits unpadded url-safe base64.
_TOKEN_BYTES = 32
DEFAULT_INVITE_TTL = timedelta(days=14)

Clock = Callable[[], datetime]
TokenFactory = Callable[[], str]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def generate_invite_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_invite_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def verify_invite_token(token: str, token_hash: bytes) -> bool:
    try:
        candidate = hash_invite_token(token)
    except UnicodeEncodeError:
        # Real tokens are always ASCII; anything else can be rejected outright.
        return False
    return hmac.compare_digest(candidate, token_hash)


def build_activation_url(base_url: str, token: str) -> str:
    # quote (not quote_plus) so the token round-trips byte-for-byte percent-encoded.
    query = urlencode({"token": token}, quote_via=quote)
    return f"{base_url.rstrip('/')}/activate?{query}"


@dataclass(frozen=True, slots=True)
class InviteGrant:
    """The one-time handoff of a freshly created invite to its caller."""

    invite: Invite
    token: str
    activation_url: str


async def create_invite(
    session: AsyncSession,
    *,
    email: str,
    created_by: str,
    activation_base_url: str,
    expires_in: timedelta = DEFAULT_INVITE_TTL,
    clock: Clock = _utcnow,
    token_factory: TokenFactory = generate_invite_token,
) -> InviteGrant:
    """Persist a hashed invite and return the raw token exactly once.

    Flushes but never commits: the caller owns the transaction boundary.
    """
    token = token_factory()
    invite = Invite(
        email=email,
        token_hash=hash_invite_token(token),
        created_by=created_by,
        expires_at=clock() + expires_in,
    )
    session.add(invite)
    await session.flush()
    return InviteGrant(
        invite=invite,
        token=token,
        activation_url=build_activation_url(activation_base_url, token),
    )
