"""POST /auth/refresh and POST /auth/logout end to end (Task B4, slice B2).

Contracts under test:
- Both endpoints demand an Origin header that exactly matches one configured
  frontend origin (normalized scheme/host/port, never substring or prefix),
  and the check runs before the refresh cookie is read or rotated: a
  disallowed Origin can never change a session row.
- Refresh reads only the hardened `bv_refresh` cookie. Missing, unknown,
  revoked, and expired tokens share one byte-identical 401
  AUTH_SESSION_REVOKED envelope; reuse of a rotated token commits the family
  revocation and an auth.refresh_reuse audit before that same 401.
- A valid refresh rotates exactly once, keeps the family's absolute expiry,
  returns {access_token, token_type, expires_in} and re-sets the hardened
  cookie whose Max-Age is the REMAINING family lifetime, never a fresh 30d.
- The access token's role comes from the users row at refresh time; deleted,
  unverified, and vanished users get a generic 401 and a revoked family.
- Logout is idempotent: known tokens revoke the whole family and audit
  auth.logout; unknown/missing/already-revoked answer the same 204. The
  cookie is always cleared with the same hardened attributes.
- Forced audit failures roll back rotation/revocation and return a safe 500.
"""

import hashlib
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from http.cookies import SimpleCookie

import httpx
import pytest
import sqlalchemy as sa

from app.config import Settings
from app.db import build_engine, build_sessionmaker
from app.main import create_app
from app.security.passwords import hash_password
from app.security.tokens import decode_access_token

REFRESH = "/auth/refresh"
LOGOUT = "/auth/logout"
LOGIN = "/auth/login"
PASSWORD = "correct-horse-battery-staple"
JWT_SECRET = "test-refresh-jwt-secret-0123456789abcdef0123456789abcdef"
ORIGIN = "http://localhost:5173"
SECOND_ORIGIN = "https://app.bevosita.example"
REFRESH_COOKIE_MAX_AGE = int(timedelta(days=30).total_seconds())

PASSWORD_HASH = hash_password(PASSWORD)

TRACEBACK_MARKERS = ("Traceback", "RuntimeError", "asyncpg", "sqlalchemy", "argon2")


def unique_email(prefix: str = "refresh") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


@asynccontextmanager
async def open_client(database_url: str, *, raise_app_exceptions: bool = True):
    settings = Settings(
        _env_file=None,
        env="test",
        database_url=database_url,
        jwt_secret=JWT_SECRET,
        frontend_origins=(ORIGIN, SECOND_ORIGIN),
    )
    app = create_app(settings)
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
) -> uuid.UUID:
    verified_sql = "now()" if verified else "NULL"
    async with build_sessionmaker(engine)() as session:
        result = await session.execute(
            sa.text(
                "INSERT INTO users (email, password_hash, full_name, role, email_verified_at) "
                f"VALUES (:email, :password_hash, 'Refresh User', CAST(:role AS user_role), "
                f"{verified_sql}) RETURNING id"
            ),
            {"email": email, "password_hash": PASSWORD_HASH, "role": role},
        )
        user_id = result.scalar_one()
        await session.commit()
        return user_id


async def execute_sql(engine, query: str, **params) -> None:
    async with engine.begin() as conn:
        await conn.execute(sa.text(query), params)


async def fetch_all(engine, query: str, **params) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(sa.text(query), params)
        return [dict(row) for row in result.mappings()]


async def fetch_sessions(engine, user_id: uuid.UUID) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, user_id, family_id, token_hash, expires_at, rotated_at, revoked_at "
        "FROM auth_sessions WHERE user_id = :user_id ORDER BY created_at, id",
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


async def login(client, email: str) -> str:
    """Log in and return the raw refresh token from the Set-Cookie header."""
    response = await client.post(LOGIN, json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return refresh_cookie_morsel(response).value


def refresh_cookie_morsel(response: httpx.Response):
    header = response.headers.get("set-cookie")
    assert header, "the endpoint must set the bv_refresh cookie"
    cookie = SimpleCookie()
    cookie.load(header)
    assert list(cookie) == ["bv_refresh"], "only the bv_refresh cookie may be set"
    return cookie["bv_refresh"]


def auth_headers(
    *, token: str | None, origin: str | None = ORIGIN, request_id: str | None = None
) -> dict:
    headers: dict[str, str] = {}
    if token is not None:
        headers["Cookie"] = f"bv_refresh={token}"
    if origin is not None:
        headers["Origin"] = origin
    if request_id is not None:
        headers["X-Request-ID"] = request_id
    return headers


def assert_error_envelope(response: httpx.Response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}, "errors must use only the canonical envelope"
    error = body["error"]
    assert error["code"] == code
    assert error["message_key"].startswith("errors.")
    assert error["request_id"]
    return error


class TestRefreshOrigin:
    async def test_missing_origin_is_rejected_before_touching_the_session(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await login(client, email)

        response = await client.post(REFRESH, headers=auth_headers(token=token, origin=None))

        assert_error_envelope(response, 403, "FORBIDDEN_ORIGIN")
        (row,) = await fetch_sessions(engine, user_id)
        assert row["rotated_at"] is None, "a rejected Origin must never rotate the session"
        assert row["revoked_at"] is None

    @pytest.mark.parametrize(
        "evil_origin",
        [
            "null",
            "https://evil.example",
            "http://localhost:5174",
            "http://localhost:51730",
            "http://localhost:5173.evil.example",
            "https://app.bevosita.example.evil.example",
            "https://evil.example/http://localhost:5173",
            "http://xlocalhost:5173",
            "https://app.bevosita.example:8443",
            "http://localhost:5173 ",
        ],
    )
    async def test_disallowed_origins_cannot_change_any_session_rows(
        self, client, engine, evil_origin
    ):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await login(client, email)

        response = await client.post(REFRESH, headers=auth_headers(token=token, origin=evil_origin))

        assert_error_envelope(response, 403, "FORBIDDEN_ORIGIN")
        (row,) = await fetch_sessions(engine, user_id)
        assert row["rotated_at"] is None
        assert row["revoked_at"] is None

    @pytest.mark.parametrize(
        "allowed_variant",
        [
            ORIGIN,
            "HTTP://LOCALHOST:5173",
            "http://localhost:5173",
            SECOND_ORIGIN,
            "https://app.bevosita.example:443",
        ],
    )
    async def test_origin_match_is_normalized_not_string_compared(
        self, client, engine, allowed_variant
    ):
        email = unique_email()
        await seed_user(engine, email)
        token = await login(client, email)

        response = await client.post(
            REFRESH, headers=auth_headers(token=token, origin=allowed_variant)
        )

        assert response.status_code == 200, response.text

    async def test_logout_requires_allowed_origin_too(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await login(client, email)

        for origin in (None, "null", "https://evil.example"):
            response = await client.post(LOGOUT, headers=auth_headers(token=token, origin=origin))
            assert_error_envelope(response, 403, "FORBIDDEN_ORIGIN")

        (row,) = await fetch_sessions(engine, user_id)
        assert row["revoked_at"] is None, "a rejected Origin must never revoke the session"


class TestRefreshSuccess:
    async def test_valid_refresh_returns_access_payload_and_rotates_once(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await login(client, email)

        response = await client.post(REFRESH, headers=auth_headers(token=token))

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"access_token", "token_type", "expires_in"}, (
            "the refresh body must carry only the access payload"
        )
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900
        claims = decode_access_token(body["access_token"], secret=JWT_SECRET)
        assert claims.user_id == user_id
        assert claims.role.value == "founder"

        parent, child = await fetch_sessions(engine, user_id)
        assert parent["rotated_at"] is not None
        assert parent["revoked_at"] is None
        assert child["rotated_at"] is None
        assert child["revoked_at"] is None
        assert child["family_id"] == parent["family_id"], "rotation stays inside the family"

    async def test_replacement_cookie_is_hardened_and_family_bound(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await login(client, email)

        response = await client.post(REFRESH, headers=auth_headers(token=token))

        assert response.status_code == 200
        morsel = refresh_cookie_morsel(response)
        new_token = morsel.value
        assert new_token and new_token != token
        assert morsel["httponly"], "the refresh cookie must be HttpOnly"
        assert morsel["secure"], "the refresh cookie must be Secure"
        assert morsel["samesite"].lower() == "none"
        assert morsel["path"] == "/auth"
        max_age = int(morsel["max-age"])
        assert 0 < max_age <= REFRESH_COOKIE_MAX_AGE
        assert max_age > REFRESH_COOKIE_MAX_AGE - 300, (
            "right after login the remaining family lifetime is still ~30 days"
        )
        assert new_token not in response.text.replace(response.headers.get("set-cookie", ""), ""), (
            "the raw token may exist only in Set-Cookie"
        )

        parent, child = await fetch_sessions(engine, user_id)
        assert child["token_hash"] == hashlib.sha256(new_token.encode("ascii")).digest()
        assert child["expires_at"] == parent["expires_at"], (
            "rotation must never extend the family's absolute expiry"
        )

    async def test_cookie_max_age_shrinks_to_remaining_family_lifetime(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await login(client, email)
        await execute_sql(
            engine,
            "UPDATE auth_sessions SET expires_at = now() + interval '10 days' "
            "WHERE user_id = :user_id",
            user_id=str(user_id),
        )

        response = await client.post(REFRESH, headers=auth_headers(token=token))

        assert response.status_code == 200
        max_age = int(refresh_cookie_morsel(response)["max-age"])
        ten_days = int(timedelta(days=10).total_seconds())
        assert ten_days - 300 < max_age <= ten_days, (
            "Max-Age must be the remaining seconds until the family expiry, not a fresh 30 days"
        )

    async def test_access_role_comes_from_the_db_row_not_stale_state(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email, role="founder")
        token = await login(client, email)
        await execute_sql(
            engine,
            "UPDATE users SET role = 'vc' WHERE id = :user_id",
            user_id=str(user_id),
        )

        response = await client.post(REFRESH, headers=auth_headers(token=token))

        assert response.status_code == 200
        claims = decode_access_token(response.json()["access_token"], secret=JWT_SECRET)
        assert claims.role.value == "vc", "the role claim must be re-read from the users row"

    async def test_success_audit_has_user_actor_and_only_family_metadata(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await login(client, email)

        response = await client.post(REFRESH, headers=auth_headers(token=token))

        assert response.status_code == 200
        (audit,) = await fetch_audit(engine, "auth.refresh", user_id)
        assert audit["actor_type"] == "user"
        assert audit["actor_id"] == user_id
        assert audit["entity_type"] == "user"
        (row, _child) = await fetch_sessions(engine, user_id)
        assert str(row["family_id"]) in audit["metadata_text"]
        assert token not in audit["metadata_text"]
        assert refresh_cookie_morsel(response).value not in audit["metadata_text"]
        assert response.json()["access_token"] not in audit["metadata_text"]


class TestRefreshFailure:
    async def test_missing_unknown_revoked_expired_are_byte_identical_401s(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        revoked_token = await login(client, email)
        expired_token = await login(client, email)
        rows = await fetch_sessions(engine, user_id)
        await execute_sql(
            engine,
            "UPDATE auth_sessions SET revoked_at = now() WHERE id = :row_id",
            row_id=str(rows[0]["id"]),
        )
        await execute_sql(
            engine,
            "UPDATE auth_sessions SET expires_at = now() - interval '1 second' WHERE id = :row_id",
            row_id=str(rows[1]["id"]),
        )

        request_id = "compare-refresh-401s"
        responses = [
            await client.post(REFRESH, headers=auth_headers(token=None, request_id=request_id)),
            await client.post(
                REFRESH,
                headers=auth_headers(token="unknown-token-value", request_id=request_id),
            ),
            await client.post(
                REFRESH, headers=auth_headers(token=revoked_token, request_id=request_id)
            ),
            await client.post(
                REFRESH, headers=auth_headers(token=expired_token, request_id=request_id)
            ),
        ]

        for response in responses:
            assert_error_envelope(response, 401, "AUTH_SESSION_REVOKED")
            assert "set-cookie" not in response.headers, (
                "refresh failures must not vary their headers by outcome"
            )
        assert len({r.content for r in responses}) == 1, (
            "the 401 bodies must not reveal whether or why the token failed"
        )

    async def test_expired_active_token_does_not_mutate_rows(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await login(client, email)
        await execute_sql(
            engine,
            "UPDATE auth_sessions SET expires_at = now() - interval '1 second' "
            "WHERE user_id = :user_id",
            user_id=str(user_id),
        )

        response = await client.post(REFRESH, headers=auth_headers(token=token))

        assert_error_envelope(response, 401, "AUTH_SESSION_REVOKED")
        (row,) = await fetch_sessions(engine, user_id)
        assert row["rotated_at"] is None
        assert row["revoked_at"] is None

    async def test_reuse_commits_family_revocation_and_audit_before_the_401(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        first_token = await login(client, email)
        rotated = await client.post(REFRESH, headers=auth_headers(token=first_token))
        assert rotated.status_code == 200
        second_token = refresh_cookie_morsel(rotated).value

        reuse = await client.post(REFRESH, headers=auth_headers(token=first_token))

        assert_error_envelope(reuse, 401, "AUTH_SESSION_REVOKED")
        rows = await fetch_sessions(engine, user_id)
        assert len(rows) == 2
        assert all(row["revoked_at"] is not None for row in rows), (
            "reuse must revoke the whole family despite the 401 response"
        )
        (audit,) = await fetch_audit(engine, "auth.refresh_reuse", user_id)
        assert audit["actor_type"] == "system"
        assert str(rows[0]["family_id"]) in audit["metadata_text"]
        assert first_token not in audit["metadata_text"]
        assert second_token not in audit["metadata_text"]
        assert first_token not in reuse.text
        assert second_token not in reuse.text

        replay_child = await client.post(REFRESH, headers=auth_headers(token=second_token))
        assert_error_envelope(replay_child, 401, "AUTH_SESSION_REVOKED")

    @pytest.mark.parametrize(
        "spoil_sql",
        [
            "UPDATE users SET deleted_at = now() WHERE id = :user_id",
            "UPDATE users SET email_verified_at = NULL WHERE id = :user_id",
        ],
    )
    async def test_deleted_or_unverified_user_gets_generic_401_and_revoked_family(
        self, client, engine, spoil_sql
    ):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await login(client, email)
        await execute_sql(engine, spoil_sql, user_id=str(user_id))

        request_id = "compare-user-state-401"
        response = await client.post(
            REFRESH, headers=auth_headers(token=token, request_id=request_id)
        )
        unknown = await client.post(
            REFRESH,
            headers=auth_headers(token="unknown-token-value", request_id=request_id),
        )

        assert_error_envelope(response, 401, "AUTH_SESSION_REVOKED")
        assert response.content == unknown.content, (
            "user-state failures must be indistinguishable from unknown tokens"
        )
        rows = await fetch_sessions(engine, user_id)
        assert all(row["revoked_at"] is not None for row in rows), (
            "a bad user state must revoke the whole family"
        )


class TestRefreshServerError:
    async def test_forced_audit_failure_rolls_back_rotation_and_returns_safe_500(
        self, test_database_url, db_at_head, engine, monkeypatch
    ):
        from app.routers import auth as auth_router_module

        email = unique_email("forced")
        user_id = await seed_user(engine, email)

        async with open_client(test_database_url, raise_app_exceptions=False) as client:
            token = await login(client, email)

            async def explode(*args, **kwargs):
                raise RuntimeError("boom-secret-marker")

            monkeypatch.setattr(auth_router_module, "write_audit", explode)
            response = await client.post(
                REFRESH, headers=auth_headers(token=token, request_id="forced-refresh-500")
            )

        assert response.status_code == 500
        error = assert_error_envelope(response, 500, "SERVER_ERROR")
        assert error["request_id"] == "forced-refresh-500"
        assert "boom-secret-marker" not in response.text
        for marker in TRACEBACK_MARKERS:
            assert marker not in response.text, f"leak marker {marker!r} in the 500 body"
        assert token not in response.text
        assert "set-cookie" not in response.headers, "a failed refresh must not set a cookie"

        (row,) = await fetch_sessions(engine, user_id)
        assert row["rotated_at"] is None, "the rotation must roll back with the failed audit"
        assert await fetch_audit(engine, "auth.refresh", user_id) == []


def cleared_cookie_morsel(response: httpx.Response):
    morsel = refresh_cookie_morsel(response)
    assert morsel.value == "", "logout must blank the cookie value"
    assert int(morsel["max-age"]) == 0
    assert morsel["path"] == "/auth"
    assert morsel["httponly"]
    assert morsel["secure"]
    assert morsel["samesite"].lower() == "none"
    return morsel


class TestLogout:
    async def test_logout_revokes_family_clears_cookie_and_audits(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await login(client, email)

        response = await client.post(LOGOUT, headers=auth_headers(token=token))

        assert response.status_code == 204
        assert response.content == b"", "logout must not return a body"
        cleared_cookie_morsel(response)
        (row,) = await fetch_sessions(engine, user_id)
        assert row["revoked_at"] is not None, "logout revocation must persist"
        (audit,) = await fetch_audit(engine, "auth.logout", user_id)
        assert audit["actor_type"] == "user"
        assert audit["actor_id"] == user_id
        assert str(row["family_id"]) in audit["metadata_text"]
        assert token not in audit["metadata_text"]

    async def test_logout_with_rotated_parent_token_revokes_the_whole_family(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        first_token = await login(client, email)
        rotated = await client.post(REFRESH, headers=auth_headers(token=first_token))
        assert rotated.status_code == 200

        response = await client.post(LOGOUT, headers=auth_headers(token=first_token))

        assert response.status_code == 204
        rows = await fetch_sessions(engine, user_id)
        assert len(rows) == 2
        assert all(row["revoked_at"] is not None for row in rows), (
            "logout with any family member must revoke every row in the family"
        )

    async def test_logout_without_cookie_is_idempotent_and_clears(self, client, engine):
        before = await fetch_all(engine, "SELECT count(*) AS n FROM audit_log")

        response = await client.post(LOGOUT, headers=auth_headers(token=None))

        assert response.status_code == 204
        assert response.content == b""
        cleared_cookie_morsel(response)
        after = await fetch_all(engine, "SELECT count(*) AS n FROM audit_log")
        assert after[0]["n"] == before[0]["n"], "a no-op logout must not audit"

    async def test_logout_with_unknown_or_already_revoked_token_stays_silent(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await login(client, email)
        first = await client.post(LOGOUT, headers=auth_headers(token=token))
        assert first.status_code == 204

        second = await client.post(LOGOUT, headers=auth_headers(token=token))
        unknown = await client.post(LOGOUT, headers=auth_headers(token="unknown-token-value"))

        assert second.status_code == 204
        assert unknown.status_code == 204
        cleared_cookie_morsel(second)
        cleared_cookie_morsel(unknown)
        audits = await fetch_audit(engine, "auth.logout", user_id)
        assert len(audits) == 1, "repeat logouts must not add audits or reveal state"

    async def test_forced_audit_failure_rolls_back_the_revocation(
        self, test_database_url, db_at_head, engine, monkeypatch
    ):
        from app.routers import auth as auth_router_module

        email = unique_email("forced-logout")
        user_id = await seed_user(engine, email)

        async with open_client(test_database_url, raise_app_exceptions=False) as client:
            token = await login(client, email)

            async def explode(*args, **kwargs):
                raise RuntimeError("boom-secret-marker")

            monkeypatch.setattr(auth_router_module, "write_audit", explode)
            response = await client.post(
                LOGOUT, headers=auth_headers(token=token, request_id="forced-logout-500")
            )

        error = assert_error_envelope(response, 500, "SERVER_ERROR")
        assert error["request_id"] == "forced-logout-500"
        assert "boom-secret-marker" not in response.text
        assert token not in response.text

        (row,) = await fetch_sessions(engine, user_id)
        assert row["revoked_at"] is None, "the revocation must roll back with the failed audit"
        assert await fetch_audit(engine, "auth.logout", user_id) == []
