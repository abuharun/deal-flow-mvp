"""Access JWT behavior (Task B4, slice A) — pure, no DB, no IO.

Access tokens are short-lived HS256 JWTs pinned to this API's issuer/audience.
Decoding is strict: signature, algorithm, issuer, audience, typ, UUID-shaped
sub/jti and an allowed role are all required, and expiry is distinguishable
from every other failure. Exception text must never carry token, secret, or
claim material — an access token in a log line is a credential leak.
"""

import base64
import dataclasses
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.models.user import UserRole
from app.security.tokens import (
    ACCESS_TOKEN_TTL,
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    AccessClaims,
    AccessTokenError,
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    generate_jti,
)

SECRET = "unit-test-secret-not-a-real-deployment-value-0123456789abcdef0123456789"
OTHER_SECRET = "a-completely-different-secret-used-to-forge-signatures-xyz987"
USER_ID = uuid.UUID("8b7a4a89-6f5e-4f3d-9c2b-1a0e9d8c7b6a")
FROZEN_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def frozen_clock() -> datetime:
    return FROZEN_NOW


def at(moment: datetime):
    return lambda: moment


def make_token(**overrides) -> str:
    return create_access_token(
        user_id=overrides.pop("user_id", USER_ID),
        role=overrides.pop("role", UserRole.FOUNDER),
        secret=overrides.pop("secret", SECRET),
        clock=overrides.pop("clock", frozen_clock),
        **overrides,
    )


def raw_payload(**overrides) -> dict:
    """A fully valid claim set for hand-crafting adversarial tokens."""
    payload = {
        "sub": str(USER_ID),
        "role": "founder",
        "jti": str(uuid.uuid4()),
        "typ": "access",
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": int(FROZEN_NOW.timestamp()),
        "nbf": int(FROZEN_NOW.timestamp()),
        "exp": int((FROZEN_NOW + ACCESS_TOKEN_TTL).timestamp()),
    }
    payload.update(overrides)
    return {k: v for k, v in payload.items() if v is not None}


def sign(payload: dict, *, secret: str = SECRET, algorithm: str = "HS256") -> str:
    return pyjwt.encode(payload, secret, algorithm=algorithm)


class TestCreateAccessToken:
    @pytest.mark.parametrize("role", [UserRole.FOUNDER, UserRole.VC])
    def test_roundtrip_returns_typed_claims_for_each_role(self, role):
        token = make_token(role=role)
        claims = decode_access_token(token, secret=SECRET, clock=frozen_clock)
        assert isinstance(claims, AccessClaims)
        assert claims.user_id == USER_ID
        assert claims.role is role
        assert isinstance(claims.jti, uuid.UUID)
        assert claims.issued_at == FROZEN_NOW
        assert claims.not_before == FROZEN_NOW
        assert claims.expires_at == FROZEN_NOW + ACCESS_TOKEN_TTL

    def test_default_ttl_is_15_minutes(self):
        assert ACCESS_TOKEN_TTL == timedelta(minutes=15)

    def test_wire_claims_are_exactly_the_planned_set(self):
        token = make_token()
        payload = pyjwt.decode(
            token,
            SECRET,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            # This test pins the wire format; FROZEN_NOW is in the real-time past.
            options={"verify_exp": False},
        )
        assert set(payload) == {"sub", "role", "jti", "typ", "iss", "aud", "iat", "nbf", "exp"}
        assert payload["sub"] == str(USER_ID)
        assert payload["role"] == "founder"
        assert payload["typ"] == "access"
        assert payload["iss"] == "bevosita-api"
        assert payload["aud"] == "bevosita-web"
        assert payload["iat"] == payload["nbf"] == int(FROZEN_NOW.timestamp())
        assert payload["exp"] == int((FROZEN_NOW + timedelta(minutes=15)).timestamp())
        uuid.UUID(payload["jti"])  # jti is a UUID string

    def test_header_pins_hs256_and_no_surprises(self):
        header = pyjwt.get_unverified_header(make_token())
        assert header["alg"] == "HS256"
        assert JWT_ALGORITHM == "HS256"

    def test_injected_jti_factory_is_used(self):
        fixed = uuid.uuid4()
        token = make_token(jti_factory=lambda: str(fixed))
        claims = decode_access_token(token, secret=SECRET, clock=frozen_clock)
        assert claims.jti == fixed

    def test_default_jti_is_a_random_uuid_per_token(self):
        jtis = {
            decode_access_token(make_token(), secret=SECRET, clock=frozen_clock).jti
            for _ in range(20)
        }
        assert len(jtis) == 20
        assert all(isinstance(j, uuid.UUID) for j in jtis)
        uuid.UUID(generate_jti())

    def test_time_injection_is_deterministic(self):
        fixed_jti = str(uuid.uuid4())
        first = make_token(jti_factory=lambda: fixed_jti)
        second = make_token(jti_factory=lambda: fixed_jti)
        assert first == second, "same clock + same jti must produce an identical token"

    def test_encoded_token_never_contains_the_secret(self):
        token = make_token()
        assert SECRET not in token
        for segment in token.split("."):
            decoded = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
            assert SECRET.encode() not in decoded

    def test_claims_are_immutable(self):
        claims = decode_access_token(make_token(), secret=SECRET, clock=frozen_clock)
        with pytest.raises(dataclasses.FrozenInstanceError):
            claims.role = UserRole.VC


class TestDecodeRejectsBadTime:
    def test_expired_token_raises_the_expired_error(self):
        token = make_token()
        with pytest.raises(ExpiredAccessTokenError):
            decode_access_token(
                token, secret=SECRET, clock=at(FROZEN_NOW + ACCESS_TOKEN_TTL + timedelta(seconds=1))
            )

    def test_expiry_boundary_is_exclusive_of_exp_itself(self):
        token = make_token()
        with pytest.raises(ExpiredAccessTokenError):
            decode_access_token(token, secret=SECRET, clock=at(FROZEN_NOW + ACCESS_TOKEN_TTL))
        claims = decode_access_token(
            token, secret=SECRET, clock=at(FROZEN_NOW + ACCESS_TOKEN_TTL - timedelta(seconds=1))
        )
        assert claims.user_id == USER_ID

    def test_token_before_nbf_is_invalid_not_expired(self):
        token = make_token()
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(token, secret=SECRET, clock=at(FROZEN_NOW - timedelta(seconds=1)))

    def test_expired_is_distinguishable_from_invalid(self):
        assert issubclass(ExpiredAccessTokenError, AccessTokenError)
        assert issubclass(InvalidAccessTokenError, AccessTokenError)
        assert not issubclass(ExpiredAccessTokenError, InvalidAccessTokenError)
        assert not issubclass(InvalidAccessTokenError, ExpiredAccessTokenError)


class TestDecodeRejectsForgeries:
    def test_wrong_issuer(self):
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(
                sign(raw_payload(iss="evil-api")), secret=SECRET, clock=frozen_clock
            )

    def test_wrong_audience(self):
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(
                sign(raw_payload(aud="evil-web")), secret=SECRET, clock=frozen_clock
            )

    def test_wrong_signature(self):
        token = sign(raw_payload(), secret=OTHER_SECRET)
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(token, secret=SECRET, clock=frozen_clock)

    def test_wrong_algorithm_even_with_the_right_secret(self):
        token = sign(raw_payload(), algorithm="HS512")
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(token, secret=SECRET, clock=frozen_clock)

    def test_none_algorithm_is_rejected(self):
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=")
        body = base64.urlsafe_b64encode(json.dumps(raw_payload()).encode()).rstrip(b"=")
        unsigned = header + b"." + body + b"."
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(unsigned.decode(), secret=SECRET, clock=frozen_clock)

    def test_wrong_typ(self):
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(sign(raw_payload(typ="refresh")), secret=SECRET, clock=frozen_clock)

    @pytest.mark.parametrize(
        "claim", ["sub", "role", "jti", "typ", "iss", "aud", "iat", "nbf", "exp"]
    )
    def test_each_missing_required_claim_is_rejected(self, claim):
        payload = raw_payload()
        del payload[claim]
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(sign(payload), secret=SECRET, clock=frozen_clock)

    def test_tampered_payload_with_original_signature(self):
        token = make_token()
        header, body, signature = token.split(".")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        payload["role"] = "vc"
        forged_body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(
                f"{header}.{forged_body}.{signature}", secret=SECRET, clock=frozen_clock
            )

    @pytest.mark.parametrize(
        "malformed",
        ["", " ", "abc", "a.b", "a.b.c", "..", "🙂🙂🙂", "Bearer abc.def.ghi", "\x00\n"],
    )
    def test_malformed_tokens_are_invalid(self, malformed):
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(malformed, secret=SECRET, clock=frozen_clock)

    def test_non_uuid_sub_is_rejected(self):
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(
                sign(raw_payload(sub="not-a-uuid")), secret=SECRET, clock=frozen_clock
            )

    def test_non_uuid_jti_is_rejected(self):
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(
                sign(raw_payload(jti="not-a-uuid")), secret=SECRET, clock=frozen_clock
            )

    @pytest.mark.parametrize("bad_role", ["admin", "FOUNDER", "", "root", 7])
    def test_disallowed_roles_are_rejected(self, bad_role):
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(sign(raw_payload(role=bad_role)), secret=SECRET, clock=frozen_clock)


class TestExceptionHygiene:
    def _texts(self, exc: BaseException) -> list[str]:
        return [str(exc), repr(exc)]

    def test_expired_error_never_leaks_token_secret_or_claims(self):
        token = make_token()
        with pytest.raises(ExpiredAccessTokenError) as excinfo:
            decode_access_token(token, secret=SECRET, clock=at(FROZEN_NOW + timedelta(hours=1)))
        for text in self._texts(excinfo.value):
            assert token not in text
            assert SECRET not in text
            assert str(USER_ID) not in text

    def test_invalid_error_never_leaks_token_secret_or_claims(self):
        token = sign(raw_payload(), secret=OTHER_SECRET)
        with pytest.raises(InvalidAccessTokenError) as excinfo:
            decode_access_token(token, secret=SECRET, clock=frozen_clock)
        for text in self._texts(excinfo.value):
            assert token not in text
            assert SECRET not in text
            assert OTHER_SECRET not in text
            assert str(USER_ID) not in text


class TestProductionSecretFloor:
    """The signing key's strength is enforced at Settings load, not here —
    prove that guarantee still holds so tokens never ship on a weak secret."""

    def test_short_production_secret_is_rejected_by_settings(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        with pytest.raises(ValidationError, match="(?i)jwt_secret"):
            Settings(
                _env_file=None,
                env="production",
                database_url="postgresql+asyncpg://app:s3cure@db.internal:5432/bevosita",
                jwt_secret="9f" * 16,  # 32 chars: below the 64-char production floor
                frontend_origins="https://bevosita.example.com",
                api_public_url="https://api.bevosita.example.com",
                frontend_public_url="https://bevosita.example.com",
            )
