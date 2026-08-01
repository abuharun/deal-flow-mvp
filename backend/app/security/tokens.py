"""Short-lived HS256 access JWTs (Task B4, slice A).

Strict decode contract: signature, pinned algorithm, issuer, audience, typ,
UUID-shaped sub/jti and an allowed role are all mandatory; expiry is the one
failure a client may act on (refresh) and gets its own exception type.

Exp/nbf are checked against an injectable clock — PyJWT's own time checks are
disabled because they read the wall clock, which tests cannot freeze.

Exception messages are fixed strings: token, secret, and claim material must
never reach logs through an error path.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt as pyjwt

from app.models.user import UserRole

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "bevosita-api"
JWT_AUDIENCE = "bevosita-web"
ACCESS_TOKEN_TTL = timedelta(minutes=15)

_REQUIRED_CLAIMS = ("sub", "role", "jti", "typ", "iss", "aud", "iat", "nbf", "exp")
_ROLE_VALUES = {member.value: member for member in UserRole}

Clock = Callable[[], datetime]
JtiFactory = Callable[[], str]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def generate_jti() -> str:
    return str(uuid.uuid4())


class AccessTokenError(Exception):
    """Base access-token failure. Messages are constants — never claim data."""


class ExpiredAccessTokenError(AccessTokenError):
    """Structurally valid token past its exp; the one case a client may refresh."""

    def __init__(self) -> None:
        super().__init__("access token expired")


class InvalidAccessTokenError(AccessTokenError):
    """Anything else: bad signature, wrong claims, malformed, not yet valid."""

    def __init__(self) -> None:
        super().__init__("access token invalid")


@dataclass(frozen=True, slots=True)
class AccessClaims:
    """Validated claims of a decoded access token."""

    user_id: uuid.UUID
    role: UserRole
    jti: uuid.UUID
    issued_at: datetime
    not_before: datetime
    expires_at: datetime


def create_access_token(
    *,
    user_id: uuid.UUID,
    role: UserRole,
    secret: str,
    clock: Clock = _utcnow,
    jti_factory: JtiFactory = generate_jti,
) -> str:
    now = int(clock().timestamp())
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "jti": jti_factory(),
        "typ": "access",
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + int(ACCESS_TOKEN_TTL.total_seconds()),
    }
    return pyjwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def _parse_uuid(value: object) -> uuid.UUID:
    if not isinstance(value, str):
        raise InvalidAccessTokenError from None
    try:
        return uuid.UUID(value)
    except ValueError:
        raise InvalidAccessTokenError from None


def _parse_timestamp(value: object) -> datetime:
    # bool is an int subclass; True would otherwise read as epoch second 1.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidAccessTokenError from None
    return datetime.fromtimestamp(value, tz=UTC)


def decode_access_token(token: str, *, secret: str, clock: Clock = _utcnow) -> AccessClaims:
    """Validate every claim and return typed claims, or raise.

    Raises ExpiredAccessTokenError only for an otherwise fully valid token
    past its exp; every other defect raises InvalidAccessTokenError.
    """
    try:
        payload = pyjwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={
                "require": list(_REQUIRED_CLAIMS),
                # Time claims are validated below against the injected clock.
                "verify_exp": False,
                "verify_nbf": False,
                "verify_iat": False,
            },
        )
    except pyjwt.PyJWTError:
        # `from None`: PyJWT error text could echo header/claim fragments.
        raise InvalidAccessTokenError from None

    if payload.get("typ") != "access":
        raise InvalidAccessTokenError from None
    role = _ROLE_VALUES.get(payload.get("role"))
    if role is None:
        raise InvalidAccessTokenError from None

    claims = AccessClaims(
        user_id=_parse_uuid(payload["sub"]),
        role=role,
        jti=_parse_uuid(payload["jti"]),
        issued_at=_parse_timestamp(payload["iat"]),
        not_before=_parse_timestamp(payload["nbf"]),
        expires_at=_parse_timestamp(payload["exp"]),
    )
    now = clock()
    if now < claims.not_before:
        raise InvalidAccessTokenError from None
    if now >= claims.expires_at:
        raise ExpiredAccessTokenError from None
    return claims
