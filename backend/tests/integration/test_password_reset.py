"""POST /auth/forgot-password and POST /auth/reset-password end to end (Task B5, slice A).

Contracts under test:
- forgot-password always answers 202 {ok: true}: unknown, soft-deleted,
  unverified, and real verified accounts produce byte-identical responses
  (given the same X-Request-ID), so the endpoint is never an existence oracle.
- A real verified account gets a newest-only RESET token (30-minute TTL) and
  a localized email in the user's stored locale, plus an
  auth.password_reset_requested audit that carries no email or token.
- A definitive email delivery failure rolls the token and audit back but
  still answers the same generic 202; a retry can issue a fresh token.
- reset-password consumes the token, stores a fresh Argon2 hash, revokes
  every refresh session of the user, and audits auth.password_reset_completed
  in one transaction. Unknown/expired tokens get a safe 422, reuse a 409, and
  bad user states a safe 422 that rolls the consumption back.
- Known boundary (documented, not invented): access JWTs issued before the
  reset remain cryptographically valid until their <=15 min expiry; only
  refresh sessions are revoked here.
- Raw reset tokens and passwords never appear in responses, audit rows, or
  the database (hashes only).
"""

import asyncio
import hashlib
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import sqlalchemy as sa

from app.config import Settings
from app.db import build_engine, build_sessionmaker
from app.main import create_app
from app.models.email_token import EmailTokenPurpose
from app.security.passwords import hash_password, verify_password
from app.security.rate_limit import RateLimiter
from app.security.tokens import decode_access_token
from app.services import password_reset_service
from app.services.email_service import (
    ConsoleEmailTransport,
    EmailDeliveryError,
    EmailMessage,
)
from app.services.email_token_service import create_email_token

FORGOT = "/auth/forgot-password"
RESET = "/auth/reset-password"
LOGIN = "/auth/login"
REFRESH = "/auth/refresh"

PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "brand-new-sunrise-passphrase"
JWT_SECRET = "test-reset-jwt-secret-0123456789abcdef0123456789abcdef"
ORIGIN = "http://localhost:5173"

PASSWORD_HASH = hash_password(PASSWORD)

TRACEBACK_MARKERS = ("Traceback", "RuntimeError", "asyncpg", "sqlalchemy", "argon2")


class FailingEmailTransport:
    """Simulates a definitive provider rejection before anything was delivered."""

    def __init__(self) -> None:
        self.attempts = 0

    async def send(self, message: EmailMessage) -> None:
        self.attempts += 1
        raise EmailDeliveryError(status_code=500, request_id="req_provider_secret_id")


def unique_email(prefix: str = "reset") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


class UnlimitedRateLimiter(RateLimiter):
    """This suite exercises the oracle/token/rollback contracts, which need
    more same-IP requests than the frozen forgot-password policy allows; the
    limiter has its own suites (test_rate_limiter, test_auth_rate_limits)."""

    async def hit(self, charges) -> None:
        return None


@asynccontextmanager
async def open_client(database_url: str, email_transport, *, raise_app_exceptions: bool = True):
    settings = Settings(
        _env_file=None,
        env="test",
        database_url=database_url,
        jwt_secret=JWT_SECRET,
        frontend_origins=(ORIGIN,),
    )
    app = create_app(settings, email_transport=email_transport, rate_limiter=UnlimitedRateLimiter())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
def outbox_transport() -> ConsoleEmailTransport:
    return ConsoleEmailTransport()


@pytest.fixture()
async def client(test_database_url, db_at_head, outbox_transport):
    async with open_client(test_database_url, outbox_transport) as c:
        yield c


async def seed_user(
    engine,
    email: str,
    *,
    verified: bool = True,
    deleted: bool = False,
    locale: str = "uz",
) -> uuid.UUID:
    verified_sql = "now()" if verified else "NULL"
    deleted_sql = "now()" if deleted else "NULL"
    async with build_sessionmaker(engine)() as session:
        result = await session.execute(
            sa.text(
                "INSERT INTO users "
                "(email, password_hash, full_name, role, locale, email_verified_at, deleted_at) "
                "VALUES (:email, :password_hash, 'Reset User', 'founder', "
                f"CAST(:locale AS ui_locale), {verified_sql}, {deleted_sql}) RETURNING id"
            ),
            {"email": email, "password_hash": PASSWORD_HASH, "locale": locale},
        )
        user_id = result.scalar_one()
        await session.commit()
        return user_id


async def seed_reset_token(
    engine, user_id: uuid.UUID, *, expires_in: timedelta = timedelta(minutes=10)
) -> str:
    async with build_sessionmaker(engine)() as session:
        grant = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.RESET, expires_in=expires_in
        )
        await session.commit()
        return grant.token


async def execute_sql(engine, query: str, **params) -> None:
    async with engine.begin() as conn:
        await conn.execute(sa.text(query), params)


async def fetch_all(engine, query: str, **params) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(sa.text(query), params)
        return [dict(row) for row in result.mappings()]


async def fetch_reset_tokens(engine, user_id: uuid.UUID) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, purpose, token_hash, expires_at, used_at FROM email_tokens "
        "WHERE user_id = :user_id AND purpose = 'reset' ORDER BY created_at, id",
        user_id=str(user_id),
    )


async def fetch_password_hash(engine, user_id: uuid.UUID) -> str:
    rows = await fetch_all(
        engine, "SELECT password_hash FROM users WHERE id = :user_id", user_id=str(user_id)
    )
    return rows[0]["password_hash"]


async def fetch_sessions(engine, user_id: uuid.UUID) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, family_id, revoked_at FROM auth_sessions "
        "WHERE user_id = :user_id ORDER BY created_at, id",
        user_id=str(user_id),
    )


async def fetch_audit(engine, action: str, entity_id) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, action, actor_type, actor_id, entity_type, entity_id, "
        "metadata::text AS metadata_text FROM audit_log "
        "WHERE action = :action AND entity_id = :entity_id",
        action=action,
        entity_id=str(entity_id),
    )


async def audit_texts_mentioning(engine, needle: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, action FROM audit_log WHERE metadata::text LIKE :pattern",
        pattern=f"%{needle}%",
    )


def sent_reset_token(transport: ConsoleEmailTransport) -> str:
    message = transport.outbox[-1]
    url_line = next(line for line in message.text.splitlines() if "/reset-password?" in line)
    return parse_qs(urlsplit(url_line).query, strict_parsing=True)["token"][0]


def assert_error_envelope(response: httpx.Response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}, "errors must use only the canonical envelope"
    error = body["error"]
    assert error["code"] == code
    assert error["message_key"].startswith("errors.")
    assert error["request_id"]
    assert response.headers["X-Request-ID"] == error["request_id"]
    return error


def assert_generic_202(response: httpx.Response) -> None:
    assert response.status_code == 202
    assert response.json() == {"ok": True}


async def login(client, email: str, password: str = PASSWORD) -> httpx.Response:
    return await client.post(LOGIN, json={"email": email, "password": password})


def refresh_token_of(response: httpx.Response) -> str:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie["bv_refresh"].value


class TestForgotPassword:
    async def test_verified_user_gets_202_reset_token_and_localized_email(
        self, client, engine, outbox_transport
    ):
        email = unique_email()
        user_id = await seed_user(engine, email, locale="ru")

        response = await client.post(FORGOT, json={"email": email})

        assert_generic_202(response)
        (token_row,) = await fetch_reset_tokens(engine, user_id)
        assert token_row["purpose"] == "reset"
        assert token_row["used_at"] is None

        (message,) = outbox_transport.outbox
        assert message.to == email
        assert "reset-password?" in message.text, "the email must carry the reset URL"
        assert re.search(r"[а-яА-ЯёЁ]", message.subject), (
            "the email must be localized from user.locale, not a default"
        )
        raw_token = sent_reset_token(outbox_transport)
        assert hashlib.sha256(raw_token.encode("ascii")).digest() == token_row["token_hash"], (
            "the database must hold only the hash of the emailed token"
        )
        assert raw_token not in response.text

    async def test_uz_locale_user_gets_uzbek_copy(self, client, engine, outbox_transport):
        email = unique_email()
        await seed_user(engine, email, locale="uz")
        response = await client.post(FORGOT, json={"email": email})
        assert_generic_202(response)
        (message,) = outbox_transport.outbox
        assert not re.search(r"[а-яА-ЯёЁ]", message.subject)

    async def test_reset_token_ttl_is_30_minutes(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        before = datetime.now(UTC)
        assert_generic_202(await client.post(FORGOT, json={"email": email}))
        (token_row,) = await fetch_reset_tokens(engine, user_id)
        ttl = token_row["expires_at"] - before
        assert timedelta(minutes=29) < ttl <= timedelta(minutes=31), (
            "RESET tokens must use the existing 30-minute TTL"
        )

    async def test_unknown_deleted_unverified_and_real_accounts_answer_identically(
        self, client, engine, outbox_transport
    ):
        real = unique_email("real")
        deleted = unique_email("deleted")
        unverified = unique_email("unverified")
        unknown = unique_email("unknown")
        await seed_user(engine, real)
        deleted_id = await seed_user(engine, deleted, deleted=True)
        unverified_id = await seed_user(engine, unverified, verified=False)

        request_id = "compare-forgot-202s"
        responses = [
            await client.post(FORGOT, json={"email": address}, headers={"X-Request-ID": request_id})
            for address in (real, deleted, unverified, unknown)
        ]

        for response in responses:
            assert_generic_202(response)
        assert len({r.content for r in responses}) == 1, (
            "the 202 bodies must be byte-identical across account states"
        )
        assert len({tuple(sorted(dict(r.headers).items())) for r in responses}) == 1, (
            "given one X-Request-ID the headers must not vary by account state"
        )

        assert await fetch_reset_tokens(engine, deleted_id) == []
        assert await fetch_reset_tokens(engine, unverified_id) == []
        assert len(outbox_transport.outbox) == 1, "only the real verified account may get email"
        assert outbox_transport.outbox[0].to == real

    async def test_internal_failure_after_lookup_is_not_an_existence_oracle(
        self, test_database_url, db_at_head, engine, monkeypatch
    ):
        """A post-lookup internal failure (here: the audit write) happens only
        for real accounts, so a 500 on that path would be an existence oracle;
        the route must roll back and answer the same generic 202."""
        real = unique_email("real")
        unknown = unique_email("unknown")
        user_id = await seed_user(engine, real)

        async def explode(*args, **kwargs):
            raise RuntimeError("boom-secret-marker")

        monkeypatch.setattr(password_reset_service, "write_audit", explode)
        request_id = "forced-forgot-oracle"
        outbox = ConsoleEmailTransport()
        async with open_client(test_database_url, outbox, raise_app_exceptions=False) as client:
            responses = [
                await client.post(
                    FORGOT, json={"email": address}, headers={"X-Request-ID": request_id}
                )
                for address in (real, unknown)
            ]

        for response in responses:
            assert_generic_202(response)
        assert len({r.content for r in responses}) == 1, (
            "the 202 bodies must be byte-identical whether or not the account exists"
        )
        assert len({tuple(sorted(dict(r.headers).items())) for r in responses}) == 1, (
            "given one X-Request-ID the headers must not vary by account state"
        )
        assert "boom-secret-marker" not in responses[0].text

        assert await fetch_reset_tokens(engine, user_id) == [], (
            "the staged token must roll back with the failed audit write"
        )
        assert await fetch_audit(engine, "auth.password_reset_requested", user_id) == []
        assert outbox.outbox == [], "no email may go out after the internal failure"

    async def test_oracle_guard_does_not_swallow_cancellation(
        self, test_database_url, db_at_head, engine, monkeypatch
    ):
        """Only Exception may be downgraded to the generic 202: cancellation
        (BaseException) must escape the route guard unanswered. The middleware
        stack surfaces the escaped cancellation as an app-level error, never
        as a fabricated success body."""
        real = unique_email("real")
        user_id = await seed_user(engine, real)

        async def explode(*args, **kwargs):
            raise asyncio.CancelledError()

        monkeypatch.setattr(password_reset_service, "write_audit", explode)
        async with open_client(
            test_database_url, ConsoleEmailTransport(), raise_app_exceptions=False
        ) as client:
            response = await client.post(FORGOT, json={"email": real})
        assert response.status_code != 202, (
            "cancellation must not be converted into the generic 202"
        )
        assert await fetch_reset_tokens(engine, user_id) == []

    async def test_ineligible_accounts_leave_no_email_in_any_audit_row(self, client, engine):
        deleted = unique_email("deleted")
        unverified = unique_email("unverified")
        unknown = unique_email("unknown")
        deleted_id = await seed_user(engine, deleted, deleted=True)
        unverified_id = await seed_user(engine, unverified, verified=False)

        for address in (deleted, unverified, unknown):
            assert_generic_202(await client.post(FORGOT, json={"email": address}))

        for address in (deleted, unverified, unknown):
            assert await audit_texts_mentioning(engine, address) == [], (
                "submitted emails must never reach audit metadata"
            )
        for user_id in (deleted_id, unverified_id):
            assert await fetch_audit(engine, "auth.password_reset_requested", user_id) == []

    async def test_requested_audit_is_existence_safe(self, client, engine, outbox_transport):
        email = unique_email()
        user_id = await seed_user(engine, email)
        assert_generic_202(await client.post(FORGOT, json={"email": email}))

        (audit,) = await fetch_audit(engine, "auth.password_reset_requested", user_id)
        assert audit["actor_type"] in ("system", "user")
        assert audit["entity_type"] == "user"
        raw_token = sent_reset_token(outbox_transport)
        assert email not in audit["metadata_text"]
        assert raw_token not in audit["metadata_text"]

    async def test_second_request_invalidates_the_older_reset_token(
        self, client, engine, outbox_transport
    ):
        email = unique_email()
        user_id = await seed_user(engine, email)
        assert_generic_202(await client.post(FORGOT, json={"email": email}))
        assert_generic_202(await client.post(FORGOT, json={"email": email}))

        old_row, new_row = await fetch_reset_tokens(engine, user_id)
        assert old_row["used_at"] is not None, "issuing a new token must retire the old one"
        assert new_row["used_at"] is None
        assert len(outbox_transport.outbox) == 2

    async def test_email_delivery_failure_rolls_back_but_still_answers_202(
        self, test_database_url, db_at_head, engine
    ):
        failing = FailingEmailTransport()
        real = unique_email("real")
        unknown = unique_email("unknown")
        user_id = await seed_user(engine, real)

        request_id = "compare-forgot-failure"
        async with open_client(test_database_url, failing) as client:
            real_response = await client.post(
                FORGOT, json={"email": real}, headers={"X-Request-ID": request_id}
            )
            unknown_response = await client.post(
                FORGOT, json={"email": unknown}, headers={"X-Request-ID": request_id}
            )

        assert failing.attempts == 1, "only the real account should attempt a send"
        assert_generic_202(real_response)
        assert real_response.content == unknown_response.content, (
            "a provider failure must not become an existence oracle"
        )
        assert "req_provider_secret_id" not in real_response.text
        assert await fetch_reset_tokens(engine, user_id) == [], (
            "the RESET token must roll back with the failed delivery"
        )
        assert await fetch_audit(engine, "auth.password_reset_requested", user_id) == [], (
            "the audit must roll back with the failed delivery"
        )

    async def test_retry_after_delivery_failure_issues_a_fresh_token(
        self, test_database_url, db_at_head, engine, outbox_transport
    ):
        email = unique_email()
        user_id = await seed_user(engine, email)
        async with open_client(test_database_url, FailingEmailTransport()) as failing_client:
            assert_generic_202(await failing_client.post(FORGOT, json={"email": email}))
        assert await fetch_reset_tokens(engine, user_id) == []

        async with open_client(test_database_url, outbox_transport) as client:
            assert_generic_202(await client.post(FORGOT, json={"email": email}))
        (token_row,) = await fetch_reset_tokens(engine, user_id)
        assert token_row["used_at"] is None
        assert len(outbox_transport.outbox) == 1

    @pytest.mark.parametrize(
        "bad_email",
        ["", "EVIL-not-an-email", "EVIL@nodot", "a" * 250 + "@example.com"],
    )
    async def test_invalid_email_shapes_return_the_canonical_validation_envelope(
        self, client, outbox_transport, bad_email
    ):
        response = await client.post(FORGOT, json={"email": bad_email})
        error = assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert error["message_key"] == "errors.validationFailed"
        if bad_email.strip():
            assert bad_email not in response.text, "submitted values must never be echoed"
        assert outbox_transport.outbox == []

    async def test_extra_fields_are_rejected(self, client):
        response = await client.post(FORGOT, json={"email": unique_email(), "admin": True})
        assert_error_envelope(response, 422, "VALIDATION_FAILED")


class TestResetPassword:
    async def test_valid_token_resets_password_revokes_all_sessions_and_audits(
        self, client, engine, outbox_transport
    ):
        email = unique_email()
        user_id = await seed_user(engine, email)
        first_login = await login(client, email)
        assert first_login.status_code == 200
        second_login = await login(client, email)
        assert second_login.status_code == 200
        old_refresh = refresh_token_of(first_login)
        assert_generic_202(await client.post(FORGOT, json={"email": email}))
        token = sent_reset_token(outbox_transport)

        response = await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert token not in response.text
        assert NEW_PASSWORD not in response.text

        stored_hash = await fetch_password_hash(engine, user_id)
        assert stored_hash.startswith("$argon2"), "the new hash must be Argon2"
        assert NEW_PASSWORD not in stored_hash
        assert verify_password(NEW_PASSWORD, stored_hash)
        assert not verify_password(PASSWORD, stored_hash)

        (token_row,) = await fetch_reset_tokens(engine, user_id)
        assert token_row["used_at"] is not None, "the token must be consumed"

        sessions = await fetch_sessions(engine, user_id)
        assert len(sessions) == 2
        assert len({row["family_id"] for row in sessions}) == 2
        assert all(row["revoked_at"] is not None for row in sessions), (
            "every refresh family must be revoked by the reset"
        )

        (audit,) = await fetch_audit(engine, "auth.password_reset_completed", user_id)
        assert audit["actor_type"] == "user"
        assert audit["actor_id"] == user_id
        assert token not in audit["metadata_text"]
        assert NEW_PASSWORD not in audit["metadata_text"]
        assert PASSWORD not in audit["metadata_text"]

        replay = await client.post(
            REFRESH, headers={"Cookie": f"bv_refresh={old_refresh}", "Origin": ORIGIN}
        )
        assert replay.status_code == 401, "revoked refresh sessions must stop working"

        assert (await login(client, email, PASSWORD)).status_code == 401
        assert (await login(client, email, NEW_PASSWORD)).status_code == 200

    async def test_old_access_token_stays_cryptographically_valid_until_expiry(
        self, client, engine, outbox_transport
    ):
        # Known boundary, deliberately documented rather than invented away:
        # access JWTs are stateless, so one issued before the reset still
        # decodes for its remaining <=15 min lifetime. Only refresh sessions
        # are revoked; an access-side invalidation watermark is future work.
        email = unique_email()
        user_id = await seed_user(engine, email)
        login_response = await login(client, email)
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]
        assert_generic_202(await client.post(FORGOT, json={"email": email}))
        token = sent_reset_token(outbox_transport)
        reset = await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})
        assert reset.status_code == 200

        claims = decode_access_token(access_token, secret=JWT_SECRET)
        assert claims.user_id == user_id

    async def test_unknown_token_returns_safe_422(self, client):
        hostile = "EVIL-" + "a" * 40
        response = await client.post(RESET, json={"token": hostile, "new_password": NEW_PASSWORD})
        error = assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert error["message_key"] == "errors.validationFailed"
        assert hostile not in response.text
        assert NEW_PASSWORD not in response.text

    async def test_malformed_non_ascii_token_returns_safe_422(self, client):
        hostile = "тайна-" + uuid.uuid4().hex
        response = await client.post(RESET, json={"token": hostile, "new_password": NEW_PASSWORD})
        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert hostile not in response.text

    async def test_expired_token_returns_safe_422_and_changes_nothing(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await seed_reset_token(engine, user_id, expires_in=timedelta(seconds=-1))

        response = await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})

        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert token not in response.text
        (row,) = await fetch_reset_tokens(engine, user_id)
        assert row["used_at"] is None
        assert await fetch_password_hash(engine, user_id) == PASSWORD_HASH

    async def test_second_use_of_a_token_returns_409_conflict(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await seed_reset_token(engine, user_id)
        first = await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})
        assert first.status_code == 200

        second = await client.post(
            RESET, json={"token": token, "new_password": "another-fresh-passphrase"}
        )

        assert_error_envelope(second, 409, "CONFLICT")
        assert token not in second.text
        stored_hash = await fetch_password_hash(engine, user_id)
        assert verify_password(NEW_PASSWORD, stored_hash), (
            "a replayed token must not change the password again"
        )

    async def test_older_token_is_dead_after_a_newer_request(
        self, client, engine, outbox_transport
    ):
        email = unique_email()
        user_id = await seed_user(engine, email)
        assert_generic_202(await client.post(FORGOT, json={"email": email}))
        old_token = sent_reset_token(outbox_transport)
        assert_generic_202(await client.post(FORGOT, json={"email": email}))
        new_token = sent_reset_token(outbox_transport)
        assert old_token != new_token

        stale = await client.post(RESET, json={"token": old_token, "new_password": NEW_PASSWORD})
        assert_error_envelope(stale, 409, "CONFLICT")
        assert await fetch_password_hash(engine, user_id) == PASSWORD_HASH

        fresh = await client.post(RESET, json={"token": new_token, "new_password": NEW_PASSWORD})
        assert fresh.status_code == 200

    @pytest.mark.parametrize(
        "spoil_sql",
        [
            "UPDATE users SET deleted_at = now() WHERE id = :user_id",
            "UPDATE users SET email_verified_at = NULL WHERE id = :user_id",
        ],
    )
    async def test_bad_user_state_returns_safe_422_and_rolls_back_consumption(
        self, client, engine, spoil_sql
    ):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await seed_reset_token(engine, user_id)
        await execute_sql(engine, spoil_sql, user_id=str(user_id))

        response = await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})

        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        (row,) = await fetch_reset_tokens(engine, user_id)
        assert row["used_at"] is None, "a rejected reset must roll the consumption back"
        assert await fetch_password_hash(engine, user_id) == PASSWORD_HASH
        assert await fetch_audit(engine, "auth.password_reset_completed", user_id) == []

    async def test_concurrent_reset_yields_one_success_one_conflict_and_one_audit(
        self, client, engine
    ):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await seed_reset_token(engine, user_id)
        payload = {"token": token, "new_password": NEW_PASSWORD}

        responses = await asyncio.gather(
            client.post(RESET, json=payload), client.post(RESET, json=payload)
        )

        assert sorted(r.status_code for r in responses) == [200, 409]
        failed = next(r for r in responses if r.status_code == 409)
        assert failed.json()["error"]["code"] == "CONFLICT"
        audits = await fetch_audit(engine, "auth.password_reset_completed", user_id)
        assert len(audits) == 1, "a concurrent reset must not duplicate the success audit"
        assert verify_password(NEW_PASSWORD, await fetch_password_hash(engine, user_id))

    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("new_password", "EVILpw9"),  # below the 10-char floor
            ("new_password", "п" * 520),  # 1040 bytes: over the module byte cap
            ("token", ""),
            ("token", "E" * 1000),
        ],
    )
    async def test_invalid_fields_return_the_canonical_validation_envelope(
        self, client, engine, field, bad_value
    ):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await seed_reset_token(engine, user_id)
        payload = {"token": token, "new_password": NEW_PASSWORD, field: bad_value}

        response = await client.post(RESET, json=payload)

        error = assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert error["message_key"] == "errors.validationFailed"
        if bad_value.strip():
            assert bad_value not in response.text, "submitted values must never be echoed"
        assert NEW_PASSWORD not in response.text
        (row,) = await fetch_reset_tokens(engine, user_id)
        assert row["used_at"] is None
        assert await fetch_password_hash(engine, user_id) == PASSWORD_HASH

    @pytest.mark.parametrize("seam", ["write_audit", "revoke_all_user_sessions"])
    async def test_forced_failure_rolls_back_hash_token_and_revocations(
        self, test_database_url, db_at_head, engine, monkeypatch, seam
    ):
        email = unique_email("forced")
        user_id = await seed_user(engine, email)

        async with open_client(
            test_database_url, ConsoleEmailTransport(), raise_app_exceptions=False
        ) as client:
            login_response = await login(client, email)
            assert login_response.status_code == 200
            token = await seed_reset_token(engine, user_id)

            async def explode(*args, **kwargs):
                raise RuntimeError("boom-secret-marker")

            monkeypatch.setattr(password_reset_service, seam, explode)
            response = await client.post(
                RESET,
                json={"token": token, "new_password": NEW_PASSWORD},
                headers={"X-Request-ID": "forced-reset-500"},
            )

        # The catch-all answers from outside the request-id middleware, so
        # only the body (not the header) carries the request id on a 500.
        assert response.status_code == 500
        body = response.json()
        assert set(body) == {"error"}, "errors must use only the canonical envelope"
        error = body["error"]
        assert error["code"] == "SERVER_ERROR"
        assert error["message_key"] == "errors.serverError"
        assert error["request_id"] == "forced-reset-500"
        assert "boom-secret-marker" not in response.text
        for marker in TRACEBACK_MARKERS:
            assert marker not in response.text, f"leak marker {marker!r} in the 500 body"
        assert token not in response.text
        assert NEW_PASSWORD not in response.text

        assert await fetch_password_hash(engine, user_id) == PASSWORD_HASH, (
            "the password hash must roll back with the failure"
        )
        (row,) = await fetch_reset_tokens(engine, user_id)
        assert row["used_at"] is None, "the token consumption must roll back"
        (session_row,) = await fetch_sessions(engine, user_id)
        assert session_row["revoked_at"] is None, "the session revocation must roll back"
        assert await fetch_audit(engine, "auth.password_reset_completed", user_id) == []
