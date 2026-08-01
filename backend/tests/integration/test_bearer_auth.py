"""Bearer principal dependencies end to end (Task B4, slice B2).

Contracts under test:
- The Authorization header is parsed strictly as `Bearer <one token>` with a
  case-insensitive scheme; missing, malformed, multi-credential, and
  bad-signature headers share one byte-identical 401 AUTH_TOKEN_INVALID with
  `WWW-Authenticate: Bearer`, and never echo the token back.
- A structurally valid token past its exp gets 401 AUTH_TOKEN_EXPIRED.
- The principal's user is loaded from the DB per request: missing, deleted,
  and unverified users — and tokens whose role claim no longer matches the
  users row — share one byte-identical generic 401 AUTH_SESSION_REVOKED, so a
  stolen access token dies with the account and reveals nothing about why.
- require_role(*roles) gates by the DB-loaded role: wrong role gets a
  canonical 403 FORBIDDEN_ROLE envelope.

The protected routes below are test-only harness routes mounted onto the app
inside this module; no product endpoint is added by this slice.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
import pytest
import sqlalchemy as sa
from fastapi import Depends

from app.config import Settings
from app.db import build_engine, build_sessionmaker
from app.deps import CurrentPrincipal, Principal, require_role
from app.main import create_app
from app.models import UserRole
from app.security.passwords import hash_password
from app.security.tokens import create_access_token

PASSWORD = "correct-horse-battery-staple"
JWT_SECRET = "test-bearer-jwt-secret-0123456789abcdef0123456789abcdef"
ORIGIN = "http://localhost:5173"

PASSWORD_HASH = hash_password(PASSWORD)

PROTECTED = "/_test/protected"
FOUNDER_ONLY = "/_test/founder-only"
VC_ONLY = "/_test/vc-only"
ANY_ROLE = "/_test/any-role"


def unique_email(prefix: str = "bearer") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def build_app(database_url: str):
    settings = Settings(
        _env_file=None,
        env="test",
        database_url=database_url,
        jwt_secret=JWT_SECRET,
        frontend_origins=(ORIGIN,),
    )
    app = create_app(settings)

    # Test-only protected routes exercising the dependencies exactly as a
    # future product router would; the app factory itself stays untouched.
    @app.get(PROTECTED)
    async def protected(principal: CurrentPrincipal) -> dict:
        return {"user_id": str(principal.user_id), "role": principal.role.value}

    @app.get(FOUNDER_ONLY)
    async def founder_only(
        principal: Annotated[Principal, Depends(require_role(UserRole.FOUNDER))],
    ) -> dict:
        return {"role": principal.role.value}

    @app.get(VC_ONLY)
    async def vc_only(
        principal: Annotated[Principal, Depends(require_role(UserRole.VC))],
    ) -> dict:
        return {"role": principal.role.value}

    @app.get(ANY_ROLE)
    async def any_role(
        principal: Annotated[Principal, Depends(require_role(UserRole.FOUNDER, UserRole.VC))],
    ) -> dict:
        return {"role": principal.role.value}

    return app


@asynccontextmanager
async def open_client(database_url: str):
    app = build_app(database_url)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
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
                f"VALUES (:email, :password_hash, 'Bearer User', CAST(:role AS user_role), "
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


def mint_token(user_id: uuid.UUID, role: UserRole, *, age: timedelta | None = None) -> str:
    clock = None
    if age is not None:
        issued_at = datetime.now(UTC) - age
        clock = lambda: issued_at  # noqa: E731
    kwargs = {"clock": clock} if clock is not None else {}
    return create_access_token(user_id=user_id, role=role, secret=JWT_SECRET, **kwargs)


def bearer_headers(token: str | None, *, request_id: str | None = None) -> dict:
    headers: dict[str, str] = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
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


def assert_bearer_challenge(response: httpx.Response) -> None:
    assert response.headers.get("www-authenticate") == "Bearer", (
        "401s from the bearer scheme must carry a WWW-Authenticate: Bearer challenge"
    )


class TestBearerSuccess:
    async def test_valid_token_yields_the_db_backed_principal(self, client, engine):
        user_id = await seed_user(engine, unique_email(), role="founder")
        token = mint_token(user_id, UserRole.FOUNDER)

        response = await client.get(PROTECTED, headers=bearer_headers(token))

        assert response.status_code == 200, response.text
        assert response.json() == {"user_id": str(user_id), "role": "founder"}

    async def test_login_issued_access_token_authenticates(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email, role="vc")
        login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
        assert login.status_code == 200

        response = await client.get(PROTECTED, headers=bearer_headers(login.json()["access_token"]))

        assert response.status_code == 200
        assert response.json() == {"user_id": str(user_id), "role": "vc"}

    async def test_scheme_is_case_insensitive(self, client, engine):
        user_id = await seed_user(engine, unique_email())
        token = mint_token(user_id, UserRole.FOUNDER)

        response = await client.get(PROTECTED, headers={"Authorization": f"bEaReR {token}"})

        assert response.status_code == 200


class TestBearerTokenInvalid:
    async def test_missing_and_malformed_headers_are_byte_identical_401s(self, client, engine):
        user_id = await seed_user(engine, unique_email())
        token = mint_token(user_id, UserRole.FOUNDER)
        request_id = "compare-bearer-401s"
        malformed = [
            None,
            token,  # no scheme
            "Bearer",
            "Bearer ",
            f"Bearer  {token}",
            f"Bearer {token} extra",
            f"Bearer {token},{token}",
            f"Bearer {token}, Bearer {token}",
            f"Basic {token}",
            f"Bearer{token}",
            'Bearer "quoted"',
        ]

        responses = []
        for header in malformed:
            headers = {"X-Request-ID": request_id}
            if header is not None:
                headers["Authorization"] = header
            responses.append(await client.get(PROTECTED, headers=headers))

        for response in responses:
            assert_error_envelope(response, 401, "AUTH_TOKEN_INVALID")
            assert_bearer_challenge(response)
            assert token not in response.text, "the presented token must never be echoed"
        assert len({r.content for r in responses}) == 1, (
            "malformed-header 401s must not reveal which check failed"
        )

    async def test_garbage_and_wrong_secret_tokens_are_invalid(self, client, engine):
        user_id = await seed_user(engine, unique_email())
        forged = create_access_token(user_id=user_id, role=UserRole.FOUNDER, secret="a" * 64)

        for bad in ("not-a-jwt", forged):
            response = await client.get(PROTECTED, headers=bearer_headers(bad))
            assert_error_envelope(response, 401, "AUTH_TOKEN_INVALID")
            assert_bearer_challenge(response)
            assert bad not in response.text

    async def test_expired_token_gets_its_own_401_code(self, client, engine):
        user_id = await seed_user(engine, unique_email())
        expired = mint_token(user_id, UserRole.FOUNDER, age=timedelta(hours=1))

        response = await client.get(PROTECTED, headers=bearer_headers(expired))

        assert_error_envelope(response, 401, "AUTH_TOKEN_EXPIRED")
        assert_bearer_challenge(response)
        assert expired not in response.text


class TestBearerUserState:
    async def test_missing_deleted_unverified_and_role_drift_are_byte_identical(
        self, client, engine
    ):
        request_id = "compare-user-state-401s"

        ghost_token = mint_token(uuid.uuid4(), UserRole.FOUNDER)

        deleted_id = await seed_user(engine, unique_email("deleted"))
        deleted_token = mint_token(deleted_id, UserRole.FOUNDER)
        await execute_sql(
            engine, "UPDATE users SET deleted_at = now() WHERE id = :id", id=str(deleted_id)
        )

        unverified_id = await seed_user(engine, unique_email("unverified"), verified=False)
        unverified_token = mint_token(unverified_id, UserRole.FOUNDER)

        drifted_id = await seed_user(engine, unique_email("drifted"), role="founder")
        drifted_token = mint_token(drifted_id, UserRole.FOUNDER)
        await execute_sql(engine, "UPDATE users SET role = 'vc' WHERE id = :id", id=str(drifted_id))

        responses = [
            await client.get(PROTECTED, headers=bearer_headers(token, request_id=request_id))
            for token in (ghost_token, deleted_token, unverified_token, drifted_token)
        ]

        for response in responses:
            assert_error_envelope(response, 401, "AUTH_SESSION_REVOKED")
            assert_bearer_challenge(response)
        assert len({r.content for r in responses}) == 1, (
            "user-state 401s must not reveal whether or why the account is unusable"
        )

    async def test_soft_deleting_the_user_kills_a_previously_working_token(self, client, engine):
        user_id = await seed_user(engine, unique_email())
        token = mint_token(user_id, UserRole.FOUNDER)
        first = await client.get(PROTECTED, headers=bearer_headers(token))
        assert first.status_code == 200

        await execute_sql(
            engine, "UPDATE users SET deleted_at = now() WHERE id = :id", id=str(user_id)
        )

        second = await client.get(PROTECTED, headers=bearer_headers(token))
        assert_error_envelope(second, 401, "AUTH_SESSION_REVOKED")
        assert token not in second.text


class TestRequireRoleRoutes:
    async def test_founder_and_vc_cells(self, client, engine):
        founder_id = await seed_user(engine, unique_email("founder"), role="founder")
        vc_id = await seed_user(engine, unique_email("vc"), role="vc")
        founder = mint_token(founder_id, UserRole.FOUNDER)
        vc = mint_token(vc_id, UserRole.VC)

        cells = [
            (founder, FOUNDER_ONLY, 200),
            (founder, VC_ONLY, 403),
            (founder, ANY_ROLE, 200),
            (vc, FOUNDER_ONLY, 403),
            (vc, VC_ONLY, 200),
            (vc, ANY_ROLE, 200),
        ]
        for token, path, expected in cells:
            response = await client.get(path, headers=bearer_headers(token))
            assert response.status_code == expected, f"{path} expected {expected}: {response.text}"
            if expected == 403:
                assert_error_envelope(response, 403, "FORBIDDEN_ROLE")

    async def test_forbidden_role_envelope_is_canonical_with_request_id(self, client, engine):
        founder_id = await seed_user(engine, unique_email(), role="founder")
        token = mint_token(founder_id, UserRole.FOUNDER)

        response = await client.get(
            VC_ONLY, headers=bearer_headers(token, request_id="forbidden-role-403")
        )

        error = assert_error_envelope(response, 403, "FORBIDDEN_ROLE")
        assert error["request_id"] == "forbidden-role-403"
        assert token not in response.text

    async def test_role_gate_uses_the_db_role_not_the_stale_claim(self, client, engine):
        user_id = await seed_user(engine, unique_email(), role="founder")
        token = mint_token(user_id, UserRole.FOUNDER)
        await execute_sql(engine, "UPDATE users SET role = 'vc' WHERE id = :id", id=str(user_id))

        # The founder-role claim no longer matches the users row, so the
        # principal is refused outright rather than granted either role.
        response = await client.get(FOUNDER_ONLY, headers=bearer_headers(token))
        assert_error_envelope(response, 401, "AUTH_SESSION_REVOKED")
