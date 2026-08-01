"""Database-free login-service and login-schema invariants (Task B4, slice B1)."""

import pytest
from pydantic import ValidationError

from app.models import AuthSession, User
from app.schemas.auth import LoginRequest
from app.security.passwords import needs_rehash, verify_password
from app.services.login_service import (
    _DUMMY_PASSWORD_HASH,
    ACCESS_TOKEN_EXPIRES_IN,
    LoginOutcome,
    LoginResult,
    LoginSuccess,
)
from app.services.session_service import SessionGrant


class TestDummyHash:
    def test_dummy_hash_is_a_valid_current_argon2_hash(self):
        assert _DUMMY_PASSWORD_HASH.startswith("$argon2id$")
        assert not needs_rehash(_DUMMY_PASSWORD_HASH), (
            "the dummy hash must match current parameters so its verify cost mirrors a real user's"
        )

    def test_dummy_hash_verify_fails_without_raising(self):
        assert verify_password("definitely-not-the-fake-password", _DUMMY_PASSWORD_HASH) is False


class TestLoginResultReprSafety:
    def test_success_repr_hides_both_tokens(self):
        success = LoginSuccess(
            user=User(),
            access_token="SECRET-ACCESS-JWT",
            expires_in=ACCESS_TOKEN_EXPIRES_IN,
            refresh_grant=SessionGrant(auth_session=AuthSession(), token="SECRET-REFRESH"),
        )
        result = LoginResult(outcome=LoginOutcome.SUCCESS, success=success)
        for dumped in (repr(result), str(result), repr(success)):
            assert "SECRET-ACCESS-JWT" not in dumped
            assert "SECRET-REFRESH" not in dumped

    def test_access_token_ttl_is_fifteen_minutes(self):
        assert ACCESS_TOKEN_EXPIRES_IN == 900


class TestLoginRequestSchema:
    def _payload(self, **overrides) -> dict:
        return {"email": "founder@example.com", "password": "correct-horse", **overrides}

    def test_password_never_appears_in_repr(self):
        request = LoginRequest(**self._payload(password="SECRET-password-1"))
        assert "SECRET-password-1" not in repr(request)
        assert "SECRET-password-1" not in str(request)
        assert request.password.get_secret_value() == "SECRET-password-1"

    def test_empty_password_is_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(**self._payload(password=""))

    def test_oversized_password_is_rejected_before_any_hashing(self):
        with pytest.raises(ValidationError) as excinfo:
            LoginRequest(**self._payload(password="п" * 520))  # 1040 bytes
        assert "п" * 520 not in str(excinfo.value)

    def test_invalid_email_is_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(**self._payload(email="EVIL-not-an-email"))

    def test_overlong_email_is_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(**self._payload(email="e" * 250 + "@example.com"))

    def test_unexpected_fields_are_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(**self._payload(evil_extra="x"))
