"""The refresh-cookie helper hard-codes the hardened attributes (Task B4, slice B1).

Secure, HttpOnly, SameSite=None, Path=/auth and the 30-day Max-Age are part
of the contract shared by login/refresh/logout — the helper takes no knobs
that could weaken them.
"""

import inspect
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

import pytest
from fastapi import Response

from app.security.cookies import (
    REFRESH_COOKIE_MAX_AGE,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    clear_refresh_cookie,
    set_refresh_cookie,
)

FROZEN_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def frozen_clock() -> datetime:
    return FROZEN_NOW


def _set_and_parse(token: str, **kwargs):
    response = Response()
    set_refresh_cookie(response, token, **kwargs)
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie[REFRESH_COOKIE_NAME]


def test_cookie_name_and_scope_match_the_contract():
    assert REFRESH_COOKIE_NAME == "bv_refresh"
    assert REFRESH_COOKIE_PATH == "/auth"
    assert REFRESH_COOKIE_MAX_AGE == int(timedelta(days=30).total_seconds())


def test_cookie_carries_every_mandatory_attribute():
    morsel = _set_and_parse("raw-refresh-token-value")
    assert morsel.value == "raw-refresh-token-value"
    assert morsel["httponly"], "the refresh cookie must be HttpOnly"
    assert morsel["secure"], "the refresh cookie must be Secure"
    assert morsel["samesite"].lower() == "none"
    assert morsel["path"] == REFRESH_COOKIE_PATH
    assert int(morsel["max-age"]) == REFRESH_COOKIE_MAX_AGE


def test_helper_exposes_no_knobs_that_could_weaken_the_flags():
    params = inspect.signature(set_refresh_cookie).parameters
    for forbidden in ("secure", "httponly", "samesite"):
        assert forbidden not in params, f"{forbidden} must not be caller-controllable"


def test_urlsafe_token_round_trips_unquoted():
    token = "AbC123-_xyz" * 4
    morsel = _set_and_parse(token)
    assert morsel.value == token
    assert morsel.coded_value == token, "url-safe tokens must not be quoted or escaped"


class TestExpiryBoundMaxAge:
    """Rotation re-sets the cookie for the REMAINING family lifetime only."""

    def test_max_age_is_the_remaining_seconds_until_expires_at(self):
        expires_at = FROZEN_NOW + timedelta(days=10)
        morsel = _set_and_parse("token", expires_at=expires_at, clock=frozen_clock)
        assert int(morsel["max-age"]) == int(timedelta(days=10).total_seconds())

    def test_expiry_bound_cookie_keeps_every_hardened_attribute(self):
        morsel = _set_and_parse(
            "token", expires_at=FROZEN_NOW + timedelta(hours=1), clock=frozen_clock
        )
        assert morsel["httponly"]
        assert morsel["secure"]
        assert morsel["samesite"].lower() == "none"
        assert morsel["path"] == REFRESH_COOKIE_PATH

    def test_max_age_never_exceeds_the_thirty_day_bound(self):
        # A corrupted expires_at must not mint a longer-lived cookie.
        expires_at = FROZEN_NOW + timedelta(days=90)
        morsel = _set_and_parse("token", expires_at=expires_at, clock=frozen_clock)
        assert int(morsel["max-age"]) == REFRESH_COOKIE_MAX_AGE

    @pytest.mark.parametrize("delta", [timedelta(0), timedelta(seconds=-1), timedelta(days=-30)])
    def test_zero_or_negative_remaining_lifetime_fails_instead_of_setting(self, delta):
        response = Response()
        with pytest.raises(ValueError):
            set_refresh_cookie(response, "token", expires_at=FROZEN_NOW + delta, clock=frozen_clock)
        assert "set-cookie" not in response.headers, "no cookie may be set for a dead family"

    def test_default_call_still_sets_the_thirty_day_login_value(self):
        morsel = _set_and_parse("token")
        assert int(morsel["max-age"]) == REFRESH_COOKIE_MAX_AGE


class TestClearRefreshCookie:
    def test_clearing_uses_the_same_name_scope_and_hardened_attributes(self):
        response = Response()
        clear_refresh_cookie(response)
        cookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])
        morsel = cookie[REFRESH_COOKIE_NAME]
        assert morsel.value == ""
        assert int(morsel["max-age"]) == 0
        assert morsel["path"] == REFRESH_COOKIE_PATH
        assert morsel["httponly"]
        assert morsel["secure"]
        assert morsel["samesite"].lower() == "none"

    def test_clear_helper_exposes_no_weakening_knobs(self):
        params = inspect.signature(clear_refresh_cookie).parameters
        for forbidden in ("secure", "httponly", "samesite", "path"):
            assert forbidden not in params, f"{forbidden} must not be caller-controllable"
