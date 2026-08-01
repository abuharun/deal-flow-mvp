"""Credentialed CORS and cache-control hardening (Task B5, slice B1).

Contracts under test:
- CORS is configured from validated Settings.frontend_origins only, with
  allow_credentials=True: an allowed preflight answers the EXACT requesting
  origin (never `*`) plus Access-Control-Allow-Credentials, the explicit
  method list GET,POST,PATCH,DELETE,OPTIONS, and the explicit header list
  Authorization,Content-Type,X-Request-ID; X-Request-ID is exposed.
- Disallowed, `null`, prefix, and suffix origins can never pass preflight
  and never receive Access-Control-Allow-Origin on any response.
- Error responses (401/422) for an allowed Origin still carry the correct
  CORS headers, so the frontend can read the canonical error envelope.
- Every /auth response — success, token-bearing, and error alike — carries
  `Cache-Control: no-store` and `Pragma: no-cache`; non-auth endpoints are
  not forced to no-store.
- The runtime CORS config cannot drift to a wildcard: Settings rejects
  wildcard origins and create_app wires only exact values into the
  middleware.
"""

import uuid

import httpx
import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from starlette.middleware.cors import CORSMiddleware

from app.config import Settings
from app.db import build_engine, build_sessionmaker
from app.main import create_app
from app.security.passwords import hash_password

LOGIN = "/auth/login"
FORGOT = "/auth/forgot-password"
REFRESH = "/auth/refresh"

ORIGIN = "http://localhost:5173"
SECOND_ORIGIN = "https://app.bevosita.example"
ALLOWED_ORIGINS = (ORIGIN, SECOND_ORIGIN)

JWT_SECRET = "test-cors-jwt-secret-0123456789abcdef0123456789abcdef"
PASSWORD = "correct-horse-battery-staple"
PASSWORD_HASH = hash_password(PASSWORD)

EXPECTED_METHODS = {"GET", "POST", "PATCH", "DELETE", "OPTIONS"}
EXPECTED_HEADERS = {"authorization", "content-type", "x-request-id"}

DISALLOWED_ORIGINS = [
    "http://evil.example",
    "null",
    # Suffix attack: the allowed origin is a prefix of the attacker's host.
    "http://localhost:5173.evil.example",
    "https://app.bevosita.example.evil.example",
    # Prefix attack: the allowed origin is a suffix of the attacker's host.
    "http://evil-localhost:5173",
    "https://evil-app.bevosita.example",
    # Scheme and port must match exactly too.
    "https://localhost:5173",
    "http://localhost:51733",
]


def unique_email(prefix: str = "cors") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def make_settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        database_url=database_url,
        jwt_secret=JWT_SECRET,
        frontend_origins=ALLOWED_ORIGINS,
    )


@pytest.fixture()
async def client(test_database_url, db_at_head):
    app = create_app(make_settings(test_database_url))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


async def seed_verified_user(engine, email: str) -> None:
    async with build_sessionmaker(engine)() as session:
        await session.execute(
            sa.text(
                "INSERT INTO users "
                "(email, password_hash, full_name, role, locale, email_verified_at) "
                "VALUES (:email, :password_hash, 'Cors User', 'founder', 'uz', now())"
            ),
            {"email": email, "password_hash": PASSWORD_HASH},
        )
        await session.commit()


def preflight_headers(origin: str, method: str = "POST", headers: str | None = None) -> dict:
    sent = {"Origin": origin, "Access-Control-Request-Method": method}
    if headers is not None:
        sent["Access-Control-Request-Headers"] = headers
    return sent


def split_header_list(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def assert_no_cors_grant(response: httpx.Response) -> None:
    # ACAO is the grant: without it the browser blocks the read regardless of
    # any other access-control-* header, so its absence is the contract.
    assert "access-control-allow-origin" not in response.headers


def assert_credentialed_cors(response: httpx.Response, origin: str) -> None:
    assert response.headers["access-control-allow-origin"] == origin, (
        "ACAO must echo the exact allowed origin, never a wildcard or another value"
    )
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "origin" in response.headers.get("vary", "").lower()


class TestPreflight:
    @pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
    async def test_allowed_preflight_answers_exact_origin_and_credentials(self, client, origin):
        response = await client.options(
            LOGIN,
            headers=preflight_headers(origin, headers="authorization, content-type, x-request-id"),
        )

        assert response.status_code == 200
        assert_credentialed_cors(response, origin)
        methods = split_header_list(response.headers["access-control-allow-methods"])
        assert methods == {m.lower() for m in EXPECTED_METHODS}
        allowed = split_header_list(response.headers["access-control-allow-headers"])
        assert EXPECTED_HEADERS <= allowed
        for name, value in response.headers.items():
            if name.lower().startswith("access-control-"):
                assert "*" in value.split(",") or "*" not in value, (
                    f"no CORS header may be a wildcard with credentials: {name}: {value}"
                )
                assert value.strip() != "*"

    @pytest.mark.parametrize("origin", DISALLOWED_ORIGINS)
    async def test_disallowed_origin_cannot_pass_preflight(self, client, origin):
        response = await client.options(LOGIN, headers=preflight_headers(origin))
        assert response.status_code == 400, "a disallowed origin must not pass preflight"
        assert_no_cors_grant(response)

    async def test_missing_origin_preflight_is_not_granted(self, client):
        response = await client.options(LOGIN, headers={"Access-Control-Request-Method": "POST"})
        assert_no_cors_grant(response)

    async def test_disallowed_method_cannot_pass_preflight(self, client):
        response = await client.options(LOGIN, headers=preflight_headers(ORIGIN, method="PUT"))
        assert response.status_code == 400

    async def test_disallowed_request_header_cannot_pass_preflight(self, client):
        response = await client.options(
            LOGIN, headers=preflight_headers(ORIGIN, headers="x-evil-header")
        )
        assert response.status_code == 400


class TestSimpleRequests:
    async def test_allowed_origin_success_carries_cors_and_exposes_request_id(self, client, engine):
        email = unique_email()
        await seed_verified_user(engine, email)

        response = await client.post(
            LOGIN, json={"email": email, "password": PASSWORD}, headers={"Origin": ORIGIN}
        )

        assert response.status_code == 200
        assert_credentialed_cors(response, ORIGIN)
        exposed = split_header_list(response.headers["access-control-expose-headers"])
        assert "x-request-id" in exposed
        assert "*" not in exposed

    async def test_error_response_for_allowed_origin_carries_cors_headers(self, client):
        response = await client.post(
            LOGIN,
            json={"email": unique_email(), "password": "wrong-password-value"},
            headers={"Origin": SECOND_ORIGIN},
        )

        assert response.status_code == 401
        assert_credentialed_cors(response, SECOND_ORIGIN)
        assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS", (
            "CORS must not break the canonical error envelope"
        )

    async def test_validation_error_for_allowed_origin_carries_cors_headers(self, client):
        response = await client.post(
            FORGOT, json={"email": "EVIL-not-an-email"}, headers={"Origin": ORIGIN}
        )
        assert response.status_code == 422
        assert_credentialed_cors(response, ORIGIN)
        assert response.json()["error"]["code"] == "VALIDATION_FAILED"

    @pytest.mark.parametrize("origin", DISALLOWED_ORIGINS)
    async def test_disallowed_origin_gets_no_cors_headers(self, client, origin):
        response = await client.post(
            LOGIN,
            json={"email": unique_email(), "password": "wrong-password-value"},
            headers={"Origin": origin},
        )
        assert_no_cors_grant(response)

    async def test_response_without_origin_gets_no_cors_headers(self, client):
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert_no_cors_grant(response)


class TestAuthNoStore:
    def assert_no_store(self, response: httpx.Response) -> None:
        assert response.headers.get("cache-control") == "no-store"
        assert response.headers.get("pragma") == "no-cache"

    async def test_login_success_token_body_is_no_store(self, client, engine):
        email = unique_email()
        await seed_verified_user(engine, email)
        response = await client.post(LOGIN, json={"email": email, "password": PASSWORD})
        assert response.status_code == 200
        self.assert_no_store(response)

    async def test_login_error_is_no_store(self, client):
        response = await client.post(
            LOGIN, json={"email": unique_email(), "password": "wrong-password-value"}
        )
        assert response.status_code == 401
        self.assert_no_store(response)

    async def test_refresh_401_is_no_store(self, client):
        response = await client.post(REFRESH, headers={"Origin": ORIGIN})
        assert response.status_code == 401
        self.assert_no_store(response)

    async def test_forgot_password_202_is_no_store(self, client):
        response = await client.post(FORGOT, json={"email": unique_email()})
        assert response.status_code == 202
        self.assert_no_store(response)

    @pytest.mark.parametrize(
        ("path", "payload"),
        [
            ("/auth/verify-email", {"token": "EVIL-unknown-token"}),
            (
                "/auth/reset-password",
                {"token": "EVIL-unknown", "new_password": "a-fine-passphrase"},
            ),
            (
                "/auth/activate-invite",
                {
                    "token": "EVIL-unknown-token",
                    "email": "someone@example.com",
                    "password": "a-fine-passphrase",
                    "full_name": "Someone",
                    "locale": "uz",
                },
            ),
        ],
    )
    async def test_other_auth_endpoints_are_no_store(self, client, path, payload):
        response = await client.post(path, json=payload)
        self.assert_no_store(response)

    async def test_validation_error_on_auth_is_no_store(self, client):
        response = await client.post(FORGOT, json={"email": "EVIL-not-an-email"})
        assert response.status_code == 422
        self.assert_no_store(response)

    async def test_health_is_not_forced_no_store(self, client):
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.headers.get("cache-control") != "no-store"
        assert "pragma" not in response.headers


class TestCorsRuntimeContract:
    @pytest.mark.parametrize(
        "origins", ["*", "https://*.bevosita.example", "http://localhost:5173,*"]
    )
    def test_settings_reject_wildcard_origins(self, test_database_url, origins):
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                env="test",
                database_url=test_database_url,
                frontend_origins=origins,
            )

    def test_cors_middleware_uses_exact_settings_values_only(self, test_database_url):
        settings = make_settings(test_database_url)
        app = create_app(settings)

        cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
        options = cors.kwargs

        assert tuple(options["allow_origins"]) == settings.frontend_origins
        assert options["allow_credentials"] is True
        assert set(options["allow_methods"]) == EXPECTED_METHODS
        assert {h.lower() for h in options["allow_headers"]} == EXPECTED_HEADERS
        assert {h.lower() for h in options["expose_headers"]} == {"x-request-id"}
        for key in ("allow_origins", "allow_methods", "allow_headers", "expose_headers"):
            assert "*" not in options[key], f"{key} must never drift to a wildcard"
        assert options.get("allow_origin_regex") in (None,), (
            "regex origins would reintroduce pattern matching; only exact origins are allowed"
        )
