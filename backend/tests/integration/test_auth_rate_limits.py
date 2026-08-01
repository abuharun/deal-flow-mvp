"""Per-endpoint auth rate limits end to end (Task B5, slice B3).

Contracts under test:
- Every public auth endpoint enforces its frozen policy BEFORE any Argon2,
  database, or email work: a blocked request creates no audit, session,
  email-token, or outbox rows.
- The 429 uses the canonical envelope {error: {code: RATE_LIMITED, ...}}
  plus an integer Retry-After header, and never echoes the submitted email,
  token, or client IP.
- Login and forgot-password are limited per client IP AND per normalized
  email hash, so case variants share one bucket and one email cannot be
  hammered from many IPs; reset-password also buckets per token hash.
- A spoofed X-Forwarded-For from an untrusted peer cannot evade the IP
  bucket; behind a configured trusted proxy the forwarded client IP is the
  bucket key.
- /auth/refresh checks the Origin dependency first: forbidden origins are
  rejected without consuming the limiter.
- Logout stays unlimited (idempotent revocation is itself protective), and
  limiters are per-app-instance state, never process globals.
"""

import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
import sqlalchemy as sa

from app.config import Settings
from app.db import build_engine, build_sessionmaker
from app.main import create_app
from app.security.passwords import hash_password
from app.security.rate_limit import RateLimiter
from app.services.email_service import ConsoleEmailTransport

LOGIN = "/auth/login"
FORGOT = "/auth/forgot-password"
RESET = "/auth/reset-password"
VERIFY = "/auth/verify-email"
ACTIVATE = "/auth/activate-invite"
REFRESH = "/auth/refresh"
LOGOUT = "/auth/logout"

ORIGIN = "http://localhost:5173"
JWT_SECRET = "test-limits-jwt-secret-0123456789abcdef0123456789abcdef"
PASSWORD = "correct-horse-battery-staple"
PASSWORD_HASH = hash_password(PASSWORD)

PEER = "203.0.113.10"
OTHER_PEERS = ("203.0.113.11", "203.0.113.12", "203.0.113.13", "203.0.113.14", "203.0.113.15")


def unique_email(prefix: str = "limits") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def unique_token(prefix: str = "EVIL") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


@asynccontextmanager
async def open_app(
    database_url: str,
    *,
    email_transport=None,
    trusted_proxy_cidrs: str = "",
    rate_limiter=None,
):
    settings = Settings(
        _env_file=None,
        env="test",
        database_url=database_url,
        jwt_secret=JWT_SECRET,
        frontend_origins=(ORIGIN,),
        trusted_proxy_cidrs=trusted_proxy_cidrs,
    )
    app = create_app(
        settings,
        email_transport=email_transport or ConsoleEmailTransport(),
        rate_limiter=rate_limiter,
    )
    async with app.router.lifespan_context(app):
        yield app


@asynccontextmanager
async def peer_client(app, ip: str = PEER):
    transport = httpx.ASGITransport(app=app, client=(ip, 40000))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def app(test_database_url, db_at_head):
    async with open_app(test_database_url) as a:
        yield a


@pytest.fixture()
async def client(app):
    async with peer_client(app) as c:
        yield c


async def seed_user(engine, email: str) -> uuid.UUID:
    async with build_sessionmaker(engine)() as session:
        result = await session.execute(
            sa.text(
                "INSERT INTO users "
                "(email, password_hash, full_name, role, locale, email_verified_at) "
                "VALUES (:email, :password_hash, 'Limits User', 'founder', 'uz', now()) "
                "RETURNING id"
            ),
            {"email": email, "password_hash": PASSWORD_HASH},
        )
        user_id = result.scalar_one()
        await session.commit()
        return user_id


async def scalar(engine, query: str, **params):
    async with engine.connect() as conn:
        return (await conn.execute(sa.text(query), params)).scalar_one()


async def count_audits(engine, action: str) -> int:
    return await scalar(engine, "SELECT count(*) FROM audit_log WHERE action = :a", a=action)


async def count_sessions(engine, user_id) -> int:
    return await scalar(
        engine, "SELECT count(*) FROM auth_sessions WHERE user_id = :u", u=str(user_id)
    )


async def count_reset_tokens(engine, user_id) -> int:
    return await scalar(
        engine,
        "SELECT count(*) FROM email_tokens WHERE user_id = :u AND purpose = 'reset'",
        u=str(user_id),
    )


def assert_rate_limited(response: httpx.Response, *, max_window: int) -> dict:
    assert response.status_code == 429
    body = response.json()
    assert set(body) == {"error"}, "the 429 must use only the canonical envelope"
    error = body["error"]
    assert error["code"] == "RATE_LIMITED"
    assert error["message_key"] == "errors.rateLimited"
    assert error["request_id"]
    assert response.headers["X-Request-ID"] == error["request_id"]
    retry_after = response.headers["Retry-After"]
    assert retry_after == str(int(retry_after)), "Retry-After must be an integer"
    assert 1 <= int(retry_after) <= max_window
    return error


async def wrong_login(client, email: str, **kwargs) -> httpx.Response:
    return await client.post(
        LOGIN, json={"email": email, "password": "wrong-password-value"}, **kwargs
    )


class TestLoginLimits:
    async def test_sixth_attempt_from_one_ip_is_429_and_writes_nothing(self, client, engine):
        for _ in range(5):
            response = await wrong_login(client, unique_email())
            assert response.status_code == 401
        # Snapshot AFTER the five allowed attempts: the contract under test is
        # that the BLOCKED request writes nothing, not how many audit rows each
        # allowed failure happens to stage.
        failed_after_allowed = await count_audits(engine, "auth.login_failed")

        blocked = await wrong_login(client, unique_email("blocked"))

        assert_rate_limited(blocked, max_window=60)
        assert PEER not in blocked.text, "the client IP must never appear in the body"
        assert "blocked" not in blocked.text, "the submitted email must never appear in the body"
        assert await count_audits(engine, "auth.login_failed") == failed_after_allowed, (
            "a blocked login must not stage or commit any audit row"
        )

    async def test_blocked_valid_credentials_create_no_session(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        for _ in range(5):
            response = await client.post(LOGIN, json={"email": email, "password": PASSWORD})
            assert response.status_code == 200
        assert await count_sessions(engine, user_id) == 5

        blocked = await client.post(LOGIN, json={"email": email, "password": PASSWORD})

        assert_rate_limited(blocked, max_window=60)
        assert "access_token" not in blocked.text
        assert await count_sessions(engine, user_id) == 5, (
            "a blocked login must not create a session row"
        )

    async def test_email_bucket_spans_ips_and_case_variants(self, app):
        local = f"limits-{uuid.uuid4().hex}"
        variants = [
            f"{local}@example.com",
            f"{local.upper()}@EXAMPLE.COM",
            f"  {local}@Example.Com",
            f"{local}@example.COM",
            f"{local.capitalize()}@example.com",
        ]
        for ip, email in zip(OTHER_PEERS, variants, strict=True):
            async with peer_client(app, ip) as client:
                response = await wrong_login(client, email.strip())
                assert response.status_code == 401

        async with peer_client(app, PEER) as client:
            blocked = await wrong_login(client, f"{local}@example.com")

        assert_rate_limited(blocked, max_window=60)

    async def test_different_ips_have_independent_ip_buckets(self, app):
        # Five distinct emails exhaust PEER's IP bucket; a different peer
        # with a sixth email is untouched.
        async with peer_client(app, PEER) as client:
            for _ in range(5):
                assert (await wrong_login(client, unique_email())).status_code == 401
            assert_rate_limited(await wrong_login(client, unique_email()), max_window=60)
        async with peer_client(app, OTHER_PEERS[0]) as client:
            assert (await wrong_login(client, unique_email())).status_code == 401


class TestForgotPasswordLimits:
    async def test_fourth_request_from_one_ip_is_429_and_stages_nothing(
        self, test_database_url, db_at_head, engine
    ):
        outbox = ConsoleEmailTransport()
        real = unique_email("real")
        user_id = await seed_user(engine, real)
        requested_before = await count_audits(engine, "auth.password_reset_requested")

        async with open_app(test_database_url, email_transport=outbox) as app:
            async with peer_client(app) as client:
                assert (await client.post(FORGOT, json={"email": real})).status_code == 202
                for _ in range(2):
                    response = await client.post(FORGOT, json={"email": unique_email()})
                    assert response.status_code == 202

                blocked = await client.post(FORGOT, json={"email": real})

        assert_rate_limited(blocked, max_window=3600)
        assert real not in blocked.text
        assert len(outbox.outbox) == 1, "a blocked forgot-password must not send email"
        assert await count_reset_tokens(engine, user_id) == 1, (
            "a blocked forgot-password must not touch token rows"
        )
        assert await count_audits(engine, "auth.password_reset_requested") == requested_before + 1

    async def test_email_bucket_spans_ips(self, test_database_url, db_at_head, engine):
        outbox = ConsoleEmailTransport()
        real = unique_email("real")
        await seed_user(engine, real)

        async with open_app(test_database_url, email_transport=outbox) as app:
            for ip in OTHER_PEERS[:3]:
                async with peer_client(app, ip) as client:
                    assert (await client.post(FORGOT, json={"email": real})).status_code == 202
            async with peer_client(app, OTHER_PEERS[3]) as client:
                blocked = await client.post(FORGOT, json={"email": real.upper()})

        assert_rate_limited(blocked, max_window=3600)
        assert len(outbox.outbox) == 3


class TestTokenEndpointLimits:
    async def test_activate_invite_eleventh_attempt_is_429(self, client):
        for _ in range(10):
            response = await client.post(
                ACTIVATE,
                json={
                    "token": unique_token(),
                    "email": unique_email(),
                    "password": "a-fine-passphrase",
                    "full_name": "Limits",
                    "locale": "uz",
                },
            )
            assert response.status_code == 422
        blocked = await client.post(
            ACTIVATE,
            json={
                "token": unique_token(),
                "email": unique_email(),
                "password": "a-fine-passphrase",
                "full_name": "Limits",
                "locale": "uz",
            },
        )
        assert_rate_limited(blocked, max_window=3600)

    async def test_verify_email_eleventh_attempt_is_429(self, client):
        for _ in range(10):
            response = await client.post(VERIFY, json={"token": unique_token()})
            assert response.status_code == 422
        assert_rate_limited(
            await client.post(VERIFY, json={"token": unique_token()}), max_window=3600
        )

    async def test_reset_password_sixth_attempt_from_one_ip_is_429(self, client):
        for _ in range(5):
            response = await client.post(
                RESET, json={"token": unique_token(), "new_password": "a-fine-passphrase"}
            )
            assert response.status_code == 422
        blocked = await client.post(
            RESET, json={"token": unique_token(), "new_password": "a-fine-passphrase"}
        )
        assert_rate_limited(blocked, max_window=3600)
        assert "a-fine-passphrase" not in blocked.text

    async def test_reset_password_token_bucket_spans_ips(self, app):
        token = unique_token()
        for ip in OTHER_PEERS[:5]:
            async with peer_client(app, ip) as client:
                response = await client.post(
                    RESET, json={"token": token, "new_password": "a-fine-passphrase"}
                )
                assert response.status_code == 422
        async with peer_client(app, PEER) as client:
            blocked = await client.post(
                RESET, json={"token": token, "new_password": "a-fine-passphrase"}
            )
        assert_rate_limited(blocked, max_window=3600)
        assert token not in blocked.text


class TestRefreshLimits:
    async def test_twenty_first_refresh_from_one_ip_is_429(self, client):
        for _ in range(20):
            response = await client.post(REFRESH, headers={"Origin": ORIGIN})
            assert response.status_code == 401
        assert_rate_limited(await client.post(REFRESH, headers={"Origin": ORIGIN}), max_window=60)

    async def test_forbidden_origin_is_rejected_before_the_limiter(self, client):
        # 25 forbidden-origin requests would exceed the 20/min policy if the
        # limiter ran first; the origin dependency must answer every one.
        for _ in range(25):
            response = await client.post(REFRESH, headers={"Origin": "http://evil.example"})
            assert response.status_code == 403
        # The limiter was never charged: a full window of allowed-origin
        # attempts still fits.
        for _ in range(20):
            response = await client.post(REFRESH, headers={"Origin": ORIGIN})
            assert response.status_code == 401
        assert_rate_limited(await client.post(REFRESH, headers={"Origin": ORIGIN}), max_window=60)

    async def test_logout_is_deliberately_unlimited(self, client):
        for _ in range(25):
            response = await client.post(LOGOUT, headers={"Origin": ORIGIN})
            assert response.status_code == 204


class TestClientIpBypass:
    async def test_spoofed_xff_from_untrusted_peer_cannot_evade(self, client):
        # trusted_proxy_cidrs is empty, so X-Forwarded-For must be ignored
        # and all requests land in the direct peer's bucket.
        for index in range(5):
            response = await wrong_login(
                client, unique_email(), headers={"X-Forwarded-For": f"198.51.100.{index}"}
            )
            assert response.status_code == 401
        blocked = await wrong_login(
            client, unique_email(), headers={"X-Forwarded-For": "198.51.100.99"}
        )
        assert_rate_limited(blocked, max_window=60)

    async def test_trusted_proxy_chain_buckets_by_forwarded_client(
        self, test_database_url, db_at_head
    ):
        async with open_app(test_database_url, trusted_proxy_cidrs="127.0.0.1/32") as app:
            async with peer_client(app, "127.0.0.1") as client:
                for _ in range(5):
                    response = await wrong_login(
                        client, unique_email(), headers={"X-Forwarded-For": "198.51.100.7"}
                    )
                    assert response.status_code == 401
                blocked = await wrong_login(
                    client, unique_email(), headers={"X-Forwarded-For": "198.51.100.7"}
                )
                assert_rate_limited(blocked, max_window=60)
                # A different forwarded client is a different bucket.
                other = await wrong_login(
                    client, unique_email(), headers={"X-Forwarded-For": "198.51.100.8"}
                )
                assert other.status_code == 401


class TestLimiterIsolation:
    async def test_limits_are_per_app_instance_not_process_globals(
        self, test_database_url, db_at_head
    ):
        async with open_app(test_database_url) as first:
            async with peer_client(first) as client:
                for _ in range(5):
                    assert (await wrong_login(client, unique_email())).status_code == 401
                assert_rate_limited(await wrong_login(client, unique_email()), max_window=60)
        async with open_app(test_database_url) as second:
            async with peer_client(second) as client:
                assert (await wrong_login(client, unique_email())).status_code == 401

    async def test_create_app_uses_an_injected_limiter(self, test_database_url, db_at_head):
        injected = RateLimiter()
        async with open_app(test_database_url, rate_limiter=injected) as app:
            assert app.state.rate_limiter is injected
