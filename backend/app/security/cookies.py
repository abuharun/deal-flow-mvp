"""Refresh-token cookie contract shared by login/refresh/logout (Task B4).

The hardened attributes are hard-coded, not parameters: every setter of the
refresh cookie must emit HttpOnly + Secure + SameSite=None scoped to /auth.
SameSite=None is required because the SPA and the API live on different
origins; Secure is mandatory for SameSite=None cookies and for the token
itself.

Max-Age is bounded by the 30-day absolute session expiry. Login sets that
full value; rotation passes the family's expires_at so the replacement
cookie lives only for the REMAINING family lifetime — a rotated cookie must
never outlive (or resurrect) its family.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Response

from app.services.session_service import REFRESH_SESSION_TTL

REFRESH_COOKIE_NAME = "bv_refresh"
# Scoped to /auth so the browser attaches the token only to auth endpoints
# (refresh/logout), never to ordinary API calls.
REFRESH_COOKIE_PATH = "/auth"
REFRESH_COOKIE_MAX_AGE = int(REFRESH_SESSION_TTL.total_seconds())

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def set_refresh_cookie(
    response: Response,
    token: str,
    *,
    expires_at: datetime | None = None,
    clock: Clock = _utcnow,
) -> None:
    """Attach the raw refresh token as the hardened bv_refresh cookie.

    Without `expires_at` (login) the cookie gets the full 30-day Max-Age.
    With it (rotation) Max-Age is the remaining seconds until the family's
    absolute expiry, capped at 30 days; a dead or corrupt expiry raises
    instead of minting a cookie.
    """
    if expires_at is None:
        max_age = REFRESH_COOKIE_MAX_AGE
    else:
        max_age = min(int((expires_at - clock()).total_seconds()), REFRESH_COOKIE_MAX_AGE)
        if max_age <= 0:
            raise ValueError("refresh cookie must not be set for an expired session family")
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="none",
    )


def clear_refresh_cookie(response: Response) -> None:
    """Expire the cookie under the exact same name, scope, and attributes."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value="",
        max_age=0,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="none",
    )
