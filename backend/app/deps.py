"""FastAPI dependencies: DB sessions, origin checks, bearer principals."""

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models import User, UserRole
from app.security.client_ip import client_ip_for_request
from app.security.origins import origin_allowed
from app.security.rate_limit import RateLimitExceeded, build_auth_charges
from app.security.tokens import (
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
    decode_access_token,
)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request; the endpoint owns commit/rollback.

    Closing the session on exit rolls back anything left uncommitted, so a
    handler that raises can never leak a half-finished transaction.
    """
    async with request.app.state.sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


async def enforce_auth_rate_limit(
    request: Request, scope: str, *, email: str | None = None, token: str | None = None
) -> None:
    """Charge the per-process limiter before any Argon2/DB/email work.

    Endpoints call this first thing in the handler (after body validation,
    which supplies the email/token subjects, and after route dependencies
    such as the refresh Origin check). A blocked request answers the
    canonical 429 with an integer Retry-After and creates no rows at all;
    the raw subjects are hashed inside build_auth_charges and never stored.
    """
    charges = build_auth_charges(scope, ip=client_ip_for_request(request), email=email, token=token)
    try:
        await request.app.state.rate_limiter.hit(charges)
    except RateLimitExceeded as exc:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "errors.rateLimited",
            "too many requests; try again later",
            headers={"Retry-After": str(exc.retry_after)},
        ) from None


def require_allowed_origin(request: Request) -> None:
    """Route-level shield for endpoints acting on the ambient refresh cookie.

    Runs as a dependency, i.e. BEFORE the handler reads or rotates anything.
    Missing, `null`, and non-matching Origins all share one 403; there is no
    wildcard and no substring matching (see app.security.origins).
    """
    settings = request.app.state.settings
    if not origin_allowed(request.headers.get("origin"), settings.frontend_origins):
        raise ApiError(403, "FORBIDDEN_ORIGIN", "errors.forbiddenOrigin", "origin is not allowed")


# Exactly `Bearer <one RFC 6750 token68>`: single space, case-insensitive
# scheme, no commas/whitespace/control characters, so a header smuggling a
# second credential or parameters can never half-parse.
_BEARER_HEADER = re.compile(r"(?i:bearer) ([A-Za-z0-9\-._~+/]+=*)")

_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def _token_invalid_error() -> ApiError:
    # One fixed 401 for every parse/signature/claim defect: the response must
    # not reveal which check failed, and never echoes the presented token.
    return ApiError(
        401,
        "AUTH_TOKEN_INVALID",
        "errors.tokenInvalid",
        "access token is not valid",
        headers=_BEARER_CHALLENGE,
    )


def _principal_revoked_error() -> ApiError:
    # Shared by missing, deleted, unverified, and role-drifted users: a token
    # that outlived its account dies without revealing which state it hit.
    return ApiError(
        401,
        "AUTH_SESSION_REVOKED",
        "errors.sessionRevoked",
        "session is not valid",
        headers=_BEARER_CHALLENGE,
    )


def extract_bearer_token(header: object) -> str | None:
    """Return the single bearer credential from an Authorization header, or None."""
    if not isinstance(header, str):
        return None
    match = _BEARER_HEADER.fullmatch(header)
    return match.group(1) if match else None


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller: DB-verified identity and role.

    The user row is repr-hidden so a logged Principal can never leak the
    email or password hash; raw token material is never stored at all.
    """

    user_id: UUID
    role: UserRole
    user: User = field(repr=False)


async def get_current_principal(request: Request, session: SessionDep) -> Principal:
    """Authenticate the request's bearer token against the DB's current state.

    The role is re-read from the users row on every request — a claim that no
    longer matches the row means the grant is stale (or forged around a role
    change) and the whole token is refused, not downgraded.
    """
    token = extract_bearer_token(request.headers.get("authorization"))
    if token is None:
        raise _token_invalid_error()
    settings = request.app.state.settings
    try:
        claims = decode_access_token(token, secret=settings.jwt_secret)
    except ExpiredAccessTokenError:
        raise ApiError(
            401,
            "AUTH_TOKEN_EXPIRED",
            "errors.tokenExpired",
            "access token has expired",
            headers=_BEARER_CHALLENGE,
        ) from None
    except InvalidAccessTokenError:
        raise _token_invalid_error() from None

    user = (
        await session.execute(select(User).where(User.id == claims.user_id))
    ).scalar_one_or_none()
    if (
        user is None
        or user.deleted_at is not None
        or user.email_verified_at is None
        or user.role is not claims.role
    ):
        raise _principal_revoked_error()
    return Principal(user_id=user.id, role=user.role, user=user)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_role(*roles: UserRole) -> Callable[[Principal], Awaitable[Principal]]:
    """Dependency factory gating a route to the given DB-verified roles."""
    allowed = frozenset(roles)

    async def role_gate(principal: CurrentPrincipal) -> Principal:
        if principal.role not in allowed:
            raise ApiError(403, "FORBIDDEN_ROLE", "errors.forbiddenRole", "role is not permitted")
        return principal

    return role_gate
