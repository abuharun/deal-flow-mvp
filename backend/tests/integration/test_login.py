"""POST /auth/login end to end (Task B4, slice B1).

Contracts under test:
- A verified, non-deleted founder or VC exchanges email+password for a
  15-minute access JWT plus an `bv_refresh` HttpOnly/Secure/SameSite=None
  cookie scoped to /auth; the raw refresh token exists only in Set-Cookie.
- Unknown email, wrong password, and soft-deleted accounts share one
  byte-identical 401 AUTH_INVALID_CREDENTIALS answer, and the unknown path
  burns a dummy Argon2 verification so timing does not reveal existence.
- Failed logins commit an actor=system auth.login_failed audit that carries
  no submitted email, password, hash, or token.
- A successful login transparently upgrades an outdated Argon2 hash inside
  the same transaction; any forced failure rolls back the upgrade, the
  session, and the success audit together and returns a safe SERVER_ERROR.
"""

import hashlib
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from http.cookies import SimpleCookie

import httpx
import pytest
import sqlalchemy as sa
from argon2 import PasswordHasher

from app.config import Settings
from app.db import build_engine, build_sessionmaker
from app.main import create_app
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.tokens import decode_access_token
from app.services import login_service

LOGIN = "/auth/login"
PASSWORD = "correct-horse-battery-staple"
JWT_SECRET = "test-login-jwt-secret-0123456789abcdef0123456789abcdef"
REFRESH_COOKIE_MAX_AGE = int(timedelta(days=30).total_seconds())

# Hashed once at import: Argon2 is deliberately slow and the plaintext is
# shared by every seeded user in this module.
PASSWORD_HASH = hash_password(PASSWORD)
# Deliberately below the current parameters so needs_rehash() is true.
WEAK_PASSWORD_HASH = PasswordHasher(
    time_cost=1, memory_cost=1024, parallelism=1, salt_len=16, hash_len=32
).hash(PASSWORD)

TRACEBACK_MARKERS = ("Traceback", "RuntimeError", "asyncpg", "sqlalchemy", "argon2")


def unique_email(prefix: str = "login") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def login_payload(email: str, password: str = PASSWORD) -> dict:
    return {"email": email, "password": password}


@asynccontextmanager
async def open_client(database_url: str, *, raise_app_exceptions: bool = True):
    settings = Settings(
        _env_file=None, env="test", database_url=database_url, jwt_secret=JWT_SECRET
    )
    app = create_app(settings)
    # httpx.ASGITransport does not run startup/shutdown; drive the lifespan
    # explicitly so the engine/sessionmaker exist like in production.
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
async def client(test_database_url, db_at_head):
    async with open_client(test_database_url) as c:
        yield c


async def seed_user(
    engine,
    email: str,
    *,
    role: str = "founder",
    verified: bool = True,
    deleted: bool = False,
    password_hash: str = PASSWORD_HASH,
    full_name: str = "Login User",
    locale: str = "uz",
) -> uuid.UUID:
    verified_sql = "now()" if verified else "NULL"
    deleted_sql = "now()" if deleted else "NULL"
    async with build_sessionmaker(engine)() as session:
        result = await session.execute(
            sa.text(
                "INSERT INTO users "
                "(email, password_hash, full_name, role, locale, email_verified_at, deleted_at) "
                "VALUES (:email, :password_hash, :full_name, CAST(:role AS user_role), "
                f"CAST(:locale AS ui_locale), {verified_sql}, {deleted_sql}) RETURNING id"
            ),
            {
                "email": email,
                "password_hash": password_hash,
                "full_name": full_name,
                "role": role,
                "locale": locale,
            },
        )
        user_id = result.scalar_one()
        await session.commit()
        return user_id


async def fetch_all(engine, query: str, **params) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(sa.text(query), params)
        return [dict(row) for row in result.mappings()]


async def fetch_password_hash(engine, user_id: uuid.UUID) -> str:
    rows = await fetch_all(
        engine, "SELECT password_hash FROM users WHERE id = :user_id", user_id=str(user_id)
    )
    return rows[0]["password_hash"]


async def fetch_sessions(engine, user_id: uuid.UUID) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, user_id, family_id, token_hash, expires_at, rotated_at, revoked_at, "
        "user_agent, created_at FROM auth_sessions WHERE user_id = :user_id "
        "ORDER BY created_at, id",
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


async def fetch_failed_audits(engine) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, actor_type, actor_id, entity_type, entity_id, "
        "metadata::text AS metadata_text FROM audit_log WHERE action = 'auth.login_failed'",
    )


def refresh_cookie_morsel(response: httpx.Response):
    header = response.headers.get("set-cookie")
    assert header, "a successful login must set the refresh cookie"
    cookie = SimpleCookie()
    cookie.load(header)
    assert list(cookie) == ["bv_refresh"], "only the bv_refresh cookie may be set"
    return cookie["bv_refresh"]


def assert_error_envelope(response: httpx.Response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}, "errors must use only the canonical envelope"
    error = body["error"]
    assert error["code"] == code
    assert error["message_key"].startswith("errors.")
    assert error["request_id"]
    return error


class TestLoginSuccess:
    async def test_verified_founder_gets_access_token_and_safe_user(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email, full_name="Firdavs Founder", locale="ru")

        response = await client.post(LOGIN, json=login_payload(email))

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"access_token", "token_type", "expires_in", "user"}, (
            "the body must never carry refresh tokens or hashes"
        )
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900
        assert body["user"] == {
            "id": str(user_id),
            "email": email,
            "full_name": "Firdavs Founder",
            "role": "founder",
            "locale": "ru",
        }
        assert PASSWORD not in response.text
        assert PASSWORD_HASH not in response.text

        claims = decode_access_token(body["access_token"], secret=JWT_SECRET)
        assert claims.user_id == user_id
        assert claims.role.value == "founder"
        assert claims.expires_at - claims.issued_at == timedelta(minutes=15)

    async def test_verified_vc_gets_vc_role_in_jwt(self, client, engine):
        email = unique_email("vc")
        user_id = await seed_user(engine, email, role="vc")

        response = await client.post(LOGIN, json=login_payload(email))

        assert response.status_code == 200
        assert response.json()["user"]["role"] == "vc"
        claims = decode_access_token(response.json()["access_token"], secret=JWT_SECRET)
        assert claims.user_id == user_id
        assert claims.role.value == "vc"

    async def test_email_lookup_is_case_insensitive(self, client, engine):
        local_part = f"case-{uuid.uuid4().hex}"
        await seed_user(engine, f"{local_part}@example.com")
        response = await client.post(LOGIN, json=login_payload(f"{local_part.upper()}@Example.COM"))
        assert response.status_code == 200

    async def test_refresh_cookie_contract_and_hashed_session_row(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        long_user_agent = "UA-" + "x" * 600

        response = await client.post(
            LOGIN, json=login_payload(email), headers={"User-Agent": long_user_agent}
        )

        assert response.status_code == 200
        morsel = refresh_cookie_morsel(response)
        raw_token = morsel.value
        assert raw_token
        assert morsel["httponly"], "the refresh cookie must be HttpOnly"
        assert morsel["secure"], "the refresh cookie must be Secure"
        assert morsel["samesite"].lower() == "none"
        assert morsel["path"] == "/auth"
        assert int(morsel["max-age"]) == REFRESH_COOKIE_MAX_AGE

        assert raw_token not in response.text, "the raw token may exist only in Set-Cookie"

        (row,) = await fetch_sessions(engine, user_id)
        assert row["token_hash"] == hashlib.sha256(raw_token.encode("ascii")).digest(), (
            "the database must hold only the SHA-256 of the cookie token"
        )
        assert row["user_agent"] == long_user_agent[:512], "user agent must be truncated"
        assert row["rotated_at"] is None
        assert row["revoked_at"] is None
        # created_at is stamped by the database, expires_at by the service
        # clock; allow a small skew between the two.
        skew = row["expires_at"] - row["created_at"] - timedelta(days=30)
        assert abs(skew) < timedelta(seconds=10)

        for audit in await fetch_audit(engine, "auth.login", user_id):
            assert raw_token not in audit["metadata_text"]

    async def test_success_audit_has_user_actor_and_safe_metadata(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)

        response = await client.post(LOGIN, json=login_payload(email))

        assert response.status_code == 200
        (audit,) = await fetch_audit(engine, "auth.login", user_id)
        assert audit["actor_type"] == "user"
        assert audit["actor_id"] == user_id
        assert audit["entity_type"] == "user"
        assert PASSWORD not in audit["metadata_text"]
        assert response.json()["access_token"] not in audit["metadata_text"]
        assert refresh_cookie_morsel(response).value not in audit["metadata_text"]

    async def test_multiple_logins_create_distinct_families_and_tokens(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)

        first = await client.post(LOGIN, json=login_payload(email))
        second = await client.post(LOGIN, json=login_payload(email))

        assert first.status_code == second.status_code == 200
        assert refresh_cookie_morsel(first).value != refresh_cookie_morsel(second).value
        assert first.json()["access_token"] != second.json()["access_token"]
        rows = await fetch_sessions(engine, user_id)
        assert len(rows) == 2
        assert rows[0]["family_id"] != rows[1]["family_id"], "each login opens a new family"
        assert rows[0]["token_hash"] != rows[1]["token_hash"]

    async def test_outdated_hash_is_upgraded_transparently(self, client, engine):
        assert needs_rehash(WEAK_PASSWORD_HASH), "the seed hash must be below current parameters"
        email = unique_email()
        user_id = await seed_user(engine, email, password_hash=WEAK_PASSWORD_HASH)

        response = await client.post(LOGIN, json=login_payload(email))

        assert response.status_code == 200
        stored = await fetch_password_hash(engine, user_id)
        assert stored != WEAK_PASSWORD_HASH, "the hash must be upgraded on successful login"
        assert verify_password(PASSWORD, stored)
        assert not needs_rehash(stored)

    async def test_current_hash_is_left_untouched(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        response = await client.post(LOGIN, json=login_payload(email))
        assert response.status_code == 200
        assert await fetch_password_hash(engine, user_id) == PASSWORD_HASH


class TestLoginFailure:
    async def test_wrong_password_and_unknown_email_are_byte_identical(self, client, engine):
        email = unique_email()
        await seed_user(engine, email)
        headers = {"X-Request-ID": "compare-401-bodies"}

        wrong_password = await client.post(
            LOGIN, json=login_payload(email, "wrong-password-entirely"), headers=headers
        )
        unknown_email = await client.post(
            LOGIN, json=login_payload(unique_email("ghost")), headers=headers
        )

        assert_error_envelope(wrong_password, 401, "AUTH_INVALID_CREDENTIALS")
        assert_error_envelope(unknown_email, 401, "AUTH_INVALID_CREDENTIALS")
        assert wrong_password.content == unknown_email.content, (
            "401 bodies must not reveal whether the email exists"
        )
        assert email not in wrong_password.text

    async def test_deleted_user_with_correct_password_matches_unknown(self, client, engine):
        deleted_email = unique_email("deleted")
        await seed_user(engine, deleted_email, deleted=True)
        headers = {"X-Request-ID": "compare-deleted-vs-unknown"}

        deleted = await client.post(LOGIN, json=login_payload(deleted_email), headers=headers)
        unknown = await client.post(
            LOGIN, json=login_payload(unique_email("ghost")), headers=headers
        )

        assert_error_envelope(deleted, 401, "AUTH_INVALID_CREDENTIALS")
        assert deleted.content == unknown.content
        assert deleted_email not in deleted.text

    async def test_unverified_user_gets_email_unverified(self, client, engine):
        email = unique_email("unverified")
        user_id = await seed_user(engine, email, verified=False)

        response = await client.post(LOGIN, json=login_payload(email))

        error = assert_error_envelope(response, 401, "AUTH_EMAIL_UNVERIFIED")
        assert email not in response.text
        assert error["message_key"].startswith("errors.")
        assert await fetch_sessions(engine, user_id) == []
        assert await fetch_audit(engine, "auth.login", user_id) == []

    async def test_unknown_email_burns_dummy_argon2_verify(self, client, monkeypatch):
        calls: list[str] = []
        real_verify = login_service.verify_password

        def spy(password: str, stored_hash: str) -> bool:
            calls.append(stored_hash)
            return real_verify(password, stored_hash)

        monkeypatch.setattr(login_service, "verify_password", spy)

        response = await client.post(LOGIN, json=login_payload(unique_email("ghost")))

        assert response.status_code == 401
        assert calls == [login_service._DUMMY_PASSWORD_HASH], (
            "the unknown-email path must verify against the stable dummy hash exactly once"
        )
        assert calls[0].startswith("$argon2"), "the dummy hash must be a real Argon2 hash"

    async def test_wrong_password_verifies_against_the_stored_hash_once(
        self, client, engine, monkeypatch
    ):
        email = unique_email()
        await seed_user(engine, email)
        calls: list[str] = []
        real_verify = login_service.verify_password

        def spy(password: str, stored_hash: str) -> bool:
            calls.append(stored_hash)
            return real_verify(password, stored_hash)

        monkeypatch.setattr(login_service, "verify_password", spy)

        response = await client.post(LOGIN, json=login_payload(email, "wrong-password-entirely"))

        assert response.status_code == 401
        assert calls == [PASSWORD_HASH], "the known-user path must cost exactly one verification"

    async def test_failures_create_no_session_and_no_success_audit(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        response = await client.post(LOGIN, json=login_payload(email, "wrong-password-entirely"))
        assert response.status_code == 401
        assert await fetch_sessions(engine, user_id) == []
        assert await fetch_audit(engine, "auth.login", user_id) == []

    async def test_failed_login_commits_a_safe_system_audit(self, client, engine):
        email = unique_email()
        await seed_user(engine, email)
        before = await fetch_failed_audits(engine)

        wrong = await client.post(LOGIN, json=login_payload(email, "wrong-password-entirely"))
        unknown = await client.post(LOGIN, json=login_payload(unique_email("ghost")))

        assert wrong.status_code == unknown.status_code == 401
        after = await fetch_failed_audits(engine)
        assert len(after) == len(before) + 2, (
            "each failed login must commit exactly one auth.login_failed audit"
        )
        for row in after:
            assert row["actor_type"] == "system"
            assert "@" not in row["metadata_text"], "no submitted email may reach the audit trail"
            assert PASSWORD not in row["metadata_text"]
            assert "wrong-password-entirely" not in row["metadata_text"]
            assert "$argon2" not in row["metadata_text"]

    async def test_unverified_login_audits_safely(self, client, engine):
        email = unique_email("unverified")
        await seed_user(engine, email, verified=False)
        before = await fetch_failed_audits(engine)

        response = await client.post(LOGIN, json=login_payload(email))

        assert response.status_code == 401
        after = await fetch_failed_audits(engine)
        assert len(after) == len(before) + 1
        for row in after:
            assert email not in row["metadata_text"]
            assert PASSWORD not in row["metadata_text"]


class TestLoginValidation:
    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("email", "EVIL-not-an-email"),
            ("email", "EVIL@nodot"),
            ("email", "e" * 250 + "@example.com"),
            ("password", ""),
            ("password", "п" * 520),  # 1040 bytes: over the module byte cap
        ],
    )
    async def test_invalid_fields_return_the_canonical_validation_envelope(
        self, client, field, bad_value
    ):
        payload = {**login_payload(unique_email()), field: bad_value}

        response = await client.post(LOGIN, json=payload)

        error = assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert error["message_key"] == "errors.validationFailed"
        if bad_value.strip():
            assert bad_value not in response.text, "submitted values must never be echoed"
        assert PASSWORD not in response.text

    async def test_unexpected_fields_are_rejected(self, client):
        payload = {**login_payload(unique_email()), "evil_extra": "EVIL-value"}
        response = await client.post(LOGIN, json=payload)
        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert "EVIL-value" not in response.text


class TestLoginServerError:
    @pytest.mark.parametrize("patch_target", ["create_session", "write_audit"])
    async def test_forced_failure_rolls_back_everything_and_returns_safe_500(
        self, test_database_url, db_at_head, engine, monkeypatch, patch_target
    ):
        email = unique_email("forced")
        user_id = await seed_user(engine, email, password_hash=WEAK_PASSWORD_HASH)

        async def explode(*args, **kwargs):
            raise RuntimeError("boom-secret-marker")

        monkeypatch.setattr(login_service, patch_target, explode)

        async with open_client(test_database_url, raise_app_exceptions=False) as client:
            response = await client.post(
                LOGIN, json=login_payload(email), headers={"X-Request-ID": "forced-500"}
            )

        assert response.status_code == 500
        body = response.json()
        assert set(body) == {"error"}, "the 500 must use only the canonical envelope"
        error = body["error"]
        assert error["code"] == "SERVER_ERROR"
        assert error["message_key"].startswith("errors.")
        assert error["request_id"] == "forced-500"
        assert "boom-secret-marker" not in response.text, (
            "exception text must never reach the client"
        )
        for marker in TRACEBACK_MARKERS:
            assert marker not in response.text, f"leak marker {marker!r} in the 500 body"
        assert PASSWORD not in response.text

        assert await fetch_password_hash(engine, user_id) == WEAK_PASSWORD_HASH, (
            "the hash upgrade must roll back with the failed login"
        )
        assert await fetch_sessions(engine, user_id) == []
        assert await fetch_audit(engine, "auth.login", user_id) == []
