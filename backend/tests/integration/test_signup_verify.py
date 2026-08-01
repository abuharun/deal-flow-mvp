"""POST /auth/activate-invite and POST /auth/verify-email end to end (Task B3, slice B).

Contracts under test:
- One DB transaction per request: a successful activation commits the user,
  used invite, verification token, and audit row together; any failure —
  validation, conflict, or email delivery — leaves no partial rows behind.
- Raw invite tokens, verification tokens, and passwords never appear in
  response bodies, audit metadata, or the database (hashes only).
- Every error uses the canonical envelope and carries X-Request-ID.
"""

import asyncio
import hashlib
import json
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import sqlalchemy as sa

from app.config import Settings
from app.db import build_engine, build_sessionmaker
from app.main import create_app
from app.models.email_token import EmailTokenPurpose
from app.security.passwords import verify_password
from app.services.email_service import (
    ConsoleEmailTransport,
    EmailDeliveryError,
    EmailMessage,
)
from app.services.email_token_service import create_email_token
from app.services.invite_service import create_invite

PASSWORD = "correct-horse-battery-staple"
ACTIVATE = "/auth/activate-invite"
VERIFY = "/auth/verify-email"

DRIVER_LEAK_MARKERS = ("asyncpg", "duplicate key", "IntegrityError", "postgresql")


class FailingEmailTransport:
    """Simulates a definitive provider rejection before anything was delivered."""

    def __init__(self) -> None:
        self.attempts = 0

    async def send(self, message: EmailMessage) -> None:
        self.attempts += 1
        raise EmailDeliveryError(status_code=500, request_id="req_provider_secret_id")


def unique_email(prefix: str = "founder") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def activation_payload(invite_token: str, invite_email: str, /, **overrides) -> dict:
    return {
        "token": invite_token,
        "email": invite_email,
        "password": PASSWORD,
        "full_name": "Firdavs Founder",
        "locale": "uz",
        **overrides,
    }


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


def sent_verification_token(transport: ConsoleEmailTransport) -> str:
    (message,) = transport.outbox
    url_line = next(line for line in message.text.splitlines() if "/verify-email?" in line)
    return parse_qs(urlsplit(url_line).query, strict_parsing=True)["token"][0]


@asynccontextmanager
async def open_client(database_url: str, email_transport):
    settings = Settings(_env_file=None, env="test", database_url=database_url)
    app = create_app(settings, email_transport=email_transport)
    # httpx.ASGITransport does not run startup/shutdown; drive the lifespan
    # explicitly so the engine/sessionmaker exist like in production.
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
def outbox_transport() -> ConsoleEmailTransport:
    return ConsoleEmailTransport()


@pytest.fixture()
async def client(test_database_url, db_at_head, outbox_transport):
    async with open_client(test_database_url, outbox_transport) as c:
        yield c


async def seed_invite(
    engine,
    email: str,
    *,
    expires_in: timedelta = timedelta(days=7),
    used: bool = False,
) -> str:
    async with build_sessionmaker(engine)() as session:
        grant = await create_invite(
            session,
            email=email,
            created_by="owner@example.com",
            activation_base_url="https://app.example.test",
            expires_in=expires_in,
        )
        if used:
            grant.invite.used_at = datetime.now(UTC)
        await session.commit()
        return grant.token


async def seed_user(engine, email: str, *, deleted: bool = False) -> uuid.UUID:
    deleted_sql = "now()" if deleted else "NULL"
    async with build_sessionmaker(engine)() as session:
        result = await session.execute(
            sa.text(
                "INSERT INTO users (email, password_hash, full_name, role, deleted_at) "
                f"VALUES (:email, 'x', 'Existing User', 'founder', {deleted_sql}) RETURNING id"
            ),
            {"email": email},
        )
        user_id = result.scalar_one()
        await session.commit()
        return user_id


async def seed_verify_token(
    engine, user_id: uuid.UUID, *, expires_in: timedelta = timedelta(hours=1)
) -> str:
    async with build_sessionmaker(engine)() as session:
        grant = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, expires_in=expires_in
        )
        await session.commit()
        return grant.token


async def fetch_all(engine, query: str, **params) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(sa.text(query), params)
        return [dict(row) for row in result.mappings()]


async def fetch_user(engine, email: str) -> dict | None:
    rows = await fetch_all(
        engine,
        "SELECT id, email, password_hash, full_name, role, locale, email_verified_at, deleted_at "
        "FROM users WHERE email = :email",
        email=email,
    )
    assert len(rows) <= 1, "activation must never create a second user for one email"
    return rows[0] if rows else None


async def fetch_invites(engine, email: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, email, used_at, expires_at FROM invites "
        "WHERE email = :email ORDER BY created_at",
        email=email,
    )


async def fetch_email_tokens(engine, user_id) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, purpose, token_hash, expires_at, used_at FROM email_tokens "
        "WHERE user_id = :user_id",
        user_id=str(user_id),
    )


async def fetch_audit(engine, action: str, entity_id) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, action, actor_type, actor_id, entity_type, entity_id, metadata "
        "FROM audit_log WHERE action = :action AND entity_id = :entity_id",
        action=action,
        entity_id=str(entity_id),
    )


def metadata_text(audit_row: dict) -> str:
    value = audit_row["metadata"]
    return value if isinstance(value, str) else json.dumps(value)


class TestActivateInvite:
    async def test_valid_invite_creates_unverified_founder_and_sends_localized_email(
        self, client, engine, outbox_transport
    ):
        email = unique_email()
        invite_token = await seed_invite(engine, email)

        response = await client.post(
            ACTIVATE, json=activation_payload(invite_token, email, locale="ru")
        )

        assert response.status_code == 201
        assert response.json() == {"ok": True}
        assert invite_token not in response.text
        assert PASSWORD not in response.text
        assert response.headers["X-Request-ID"]

        user = await fetch_user(engine, email)
        assert user is not None
        assert user["role"] == "founder"
        assert user["locale"] == "ru", "user locale must come from the request"
        assert user["email_verified_at"] is None, "a fresh signup must be unverified"
        assert user["deleted_at"] is None
        assert user["password_hash"] != PASSWORD
        assert PASSWORD not in user["password_hash"]
        assert verify_password(PASSWORD, user["password_hash"])

        (invite,) = await fetch_invites(engine, email)
        assert invite["used_at"] is not None, "the invite must be consumed"

        (token_row,) = await fetch_email_tokens(engine, user["id"])
        assert token_row["purpose"] == "verify"
        assert token_row["used_at"] is None

        (message,) = outbox_transport.outbox
        assert message.to == email
        assert re.search(r"[а-яА-ЯёЁ]", message.subject), "locale=ru must localize the email"
        raw_verify_token = sent_verification_token(outbox_transport)
        assert raw_verify_token != invite_token
        assert (
            hashlib.sha256(raw_verify_token.encode("ascii")).digest() == token_row["token_hash"]
        ), "DB must hold only the hash of the emailed token"

        (audit,) = await fetch_audit(engine, "auth.signup", user["id"])
        dumped = metadata_text(audit)
        assert invite_token not in dumped, "raw invite token must never reach the audit trail"
        assert raw_verify_token not in dumped, "raw verify token must never reach the audit trail"
        assert PASSWORD not in dumped

    async def test_uz_locale_is_stored_and_email_copy_is_not_russian(
        self, client, engine, outbox_transport
    ):
        email = unique_email()
        invite_token = await seed_invite(engine, email)
        response = await client.post(
            ACTIVATE, json=activation_payload(invite_token, email, locale="uz")
        )
        assert response.status_code == 201
        user = await fetch_user(engine, email)
        assert user["locale"] == "uz"
        (message,) = outbox_transport.outbox
        assert not re.search(r"[а-яА-ЯёЁ]", message.subject)

    async def test_invite_email_match_is_case_insensitive(self, client, engine):
        local_part = f"Founder-{uuid.uuid4().hex}"
        invite_token = await seed_invite(engine, f"{local_part}@Example.com")
        response = await client.post(
            ACTIVATE,
            json=activation_payload(invite_token, f"{local_part.lower()}@example.com"),
        )
        assert response.status_code == 201

    async def test_used_invite_returns_409_invite_used(self, client, engine, outbox_transport):
        email = unique_email()
        invite_token = await seed_invite(engine, email, used=True)
        response = await client.post(ACTIVATE, json=activation_payload(invite_token, email))
        assert_error_envelope(response, 409, "INVITE_USED")
        assert invite_token not in response.text
        assert await fetch_user(engine, email) is None
        assert outbox_transport.outbox == []

    async def test_expired_invite_returns_safe_422(self, client, engine, outbox_transport):
        email = unique_email()
        invite_token = await seed_invite(engine, email, expires_in=timedelta(seconds=-1))
        response = await client.post(ACTIVATE, json=activation_payload(invite_token, email))
        error = assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert error["message_key"] == "errors.validationFailed"
        assert invite_token not in response.text
        assert await fetch_user(engine, email) is None
        assert outbox_transport.outbox == []

    async def test_unknown_invite_token_returns_safe_422(self, client, engine):
        email = unique_email()
        never_issued = "a" * 43
        response = await client.post(ACTIVATE, json=activation_payload(never_issued, email))
        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert never_issued not in response.text
        assert await fetch_user(engine, email) is None

    async def test_malformed_non_ascii_invite_token_returns_safe_422(self, client, engine):
        email = unique_email()
        hostile = "тайна-" + uuid.uuid4().hex
        response = await client.post(ACTIVATE, json=activation_payload(hostile, email))
        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert hostile not in response.text
        assert await fetch_user(engine, email) is None

    async def test_email_mismatch_returns_safe_422_without_leaking_invite_email(
        self, client, engine, outbox_transport
    ):
        invited_email = unique_email("invited")
        request_email = unique_email("other")
        invite_token = await seed_invite(engine, invited_email)
        response = await client.post(ACTIVATE, json=activation_payload(invite_token, request_email))
        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert invited_email not in response.text, "the invited email must never leak"
        assert await fetch_user(engine, request_email) is None
        (invite,) = await fetch_invites(engine, invited_email)
        assert invite["used_at"] is None
        assert outbox_transport.outbox == []

    async def test_existing_user_email_returns_409_conflict_and_commits_nothing(
        self, client, engine, outbox_transport
    ):
        email = unique_email()
        user_id = await seed_user(engine, email)
        invite_token = await seed_invite(engine, email)

        response = await client.post(ACTIVATE, json=activation_payload(invite_token, email))

        assert_error_envelope(response, 409, "CONFLICT")
        for marker in DRIVER_LEAK_MARKERS:
            assert marker not in response.text, f"driver detail {marker!r} must never leak"
        (invite,) = await fetch_invites(engine, email)
        assert invite["used_at"] is None, "the invite must stay usable"
        assert await fetch_email_tokens(engine, user_id) == []
        assert await fetch_audit(engine, "auth.signup", user_id) == []
        assert outbox_transport.outbox == []

    async def test_second_activation_of_the_same_invite_conflicts(
        self, client, engine, outbox_transport
    ):
        email = unique_email()
        invite_token = await seed_invite(engine, email)
        first = await client.post(ACTIVATE, json=activation_payload(invite_token, email))
        assert first.status_code == 201
        second = await client.post(
            ACTIVATE, json=activation_payload(invite_token, email, full_name="Second Person")
        )
        assert_error_envelope(second, 409, "INVITE_USED")
        user = await fetch_user(engine, email)
        assert user["full_name"] == "Firdavs Founder"
        assert len(outbox_transport.outbox) == 1

    async def test_concurrent_activation_of_one_invite_creates_exactly_one_user(
        self, client, engine, outbox_transport
    ):
        email = unique_email()
        invite_token = await seed_invite(engine, email)
        payload = activation_payload(invite_token, email)

        responses = await asyncio.gather(
            client.post(ACTIVATE, json=payload), client.post(ACTIVATE, json=payload)
        )

        assert sorted(r.status_code for r in responses) == [201, 409]
        failed = next(r for r in responses if r.status_code == 409)
        assert failed.json()["error"]["code"] == "INVITE_USED"
        assert await fetch_user(engine, email) is not None
        assert len(outbox_transport.outbox) == 1

    async def test_concurrent_activation_of_two_invites_for_one_email_yields_one_user(
        self, client, engine, outbox_transport
    ):
        email = unique_email()
        token_a = await seed_invite(engine, email)
        token_b = await seed_invite(engine, email)

        responses = await asyncio.gather(
            client.post(ACTIVATE, json=activation_payload(token_a, email)),
            client.post(ACTIVATE, json=activation_payload(token_b, email)),
        )

        assert sorted(r.status_code for r in responses) == [201, 409]
        failed = next(r for r in responses if r.status_code == 409)
        assert failed.json()["error"]["code"] == "CONFLICT"
        for marker in DRIVER_LEAK_MARKERS:
            assert marker not in failed.text, f"driver detail {marker!r} must never leak"
        assert await fetch_user(engine, email) is not None
        assert len(outbox_transport.outbox) == 1

    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("password", "EVILpw9"),  # below the 10-char floor
            ("password", "п" * 520),  # 1040 bytes: over the module byte cap
            ("email", "EVIL-not-an-email"),
            ("email", "EVIL@nodot"),
            ("full_name", ""),
            ("full_name", "   "),
            ("full_name", "E" * 300),
            ("locale", "EVIL-locale"),
            ("token", ""),
            ("token", "E" * 1000),
        ],
    )
    async def test_invalid_fields_return_the_canonical_validation_envelope(
        self, client, engine, outbox_transport, field, bad_value
    ):
        email = unique_email()
        invite_token = await seed_invite(engine, email)
        payload = activation_payload(invite_token, email, **{field: bad_value})

        response = await client.post(ACTIVATE, json=payload)

        error = assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert error["message_key"] == "errors.validationFailed"
        assert "detail" in error
        if bad_value.strip():
            assert bad_value not in response.text, "submitted values must never be echoed"
        assert PASSWORD not in response.text
        assert await fetch_user(engine, email) is None
        assert outbox_transport.outbox == []

    async def test_email_delivery_failure_rolls_back_the_whole_transaction(
        self, test_database_url, db_at_head, engine
    ):
        failing = FailingEmailTransport()
        email = unique_email()
        invite_token = await seed_invite(engine, email)
        audits_before = await fetch_all(
            engine, "SELECT id FROM audit_log WHERE action = 'auth.signup'"
        )
        tokens_before = await fetch_all(engine, "SELECT id FROM email_tokens")

        async with open_client(test_database_url, failing) as client:
            response = await client.post(ACTIVATE, json=activation_payload(invite_token, email))

        assert_error_envelope(response, 502, "EMAIL_DELIVERY_FAILED")
        assert failing.attempts == 1, "the send must be attempted before commit"
        for secret in ("req_provider_secret_id", email, invite_token, PASSWORD):
            assert secret not in response.text

        assert await fetch_user(engine, email) is None, "the user must be rolled back"
        (invite,) = await fetch_invites(engine, email)
        assert invite["used_at"] is None, "the invite must be rolled back to unused"
        audits_after = await fetch_all(
            engine, "SELECT id FROM audit_log WHERE action = 'auth.signup'"
        )
        assert len(audits_after) == len(audits_before), "no audit row may survive the rollback"
        tokens_after = await fetch_all(engine, "SELECT id FROM email_tokens")
        assert len(tokens_after) == len(tokens_before), "no email token may survive the rollback"


class TestVerifyEmail:
    async def test_valid_token_verifies_email_and_audits_once(
        self, client, engine, outbox_transport
    ):
        email = unique_email()
        invite_token = await seed_invite(engine, email)
        activated = await client.post(ACTIVATE, json=activation_payload(invite_token, email))
        assert activated.status_code == 201
        verify_token = sent_verification_token(outbox_transport)

        response = await client.post(VERIFY, json={"token": verify_token})

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert verify_token not in response.text

        user = await fetch_user(engine, email)
        assert user["email_verified_at"] is not None
        (token_row,) = await fetch_email_tokens(engine, user["id"])
        assert token_row["used_at"] is not None, "the token must be consumed"
        (audit,) = await fetch_audit(engine, "auth.email_verified", user["id"])
        assert verify_token not in metadata_text(audit)

    async def test_unknown_token_returns_safe_422(self, client):
        hostile = "EVIL-" + "a" * 40
        response = await client.post(VERIFY, json={"token": hostile})
        error = assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert error["message_key"] == "errors.validationFailed"
        assert hostile not in response.text

    async def test_expired_token_returns_safe_422_and_stays_unused(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        token = await seed_verify_token(engine, user_id, expires_in=timedelta(seconds=-1))
        response = await client.post(VERIFY, json={"token": token})
        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert token not in response.text
        (row,) = await fetch_email_tokens(engine, user_id)
        assert row["used_at"] is None
        user = await fetch_user(engine, email)
        assert user["email_verified_at"] is None

    async def test_second_use_of_a_token_returns_409_conflict(self, client, engine):
        user_id = await seed_user(engine, unique_email())
        token = await seed_verify_token(engine, user_id)
        first = await client.post(VERIFY, json={"token": token})
        assert first.status_code == 200
        second = await client.post(VERIFY, json={"token": token})
        assert_error_envelope(second, 409, "CONFLICT")
        assert token not in second.text

    async def test_concurrent_double_verify_yields_one_success_and_one_conflict(
        self, client, engine
    ):
        user_id = await seed_user(engine, unique_email())
        token = await seed_verify_token(engine, user_id)

        responses = await asyncio.gather(
            client.post(VERIFY, json={"token": token}),
            client.post(VERIFY, json={"token": token}),
        )

        assert sorted(r.status_code for r in responses) == [200, 409]
        failed = next(r for r in responses if r.status_code == 409)
        assert failed.json()["error"]["code"] == "CONFLICT"
        audits = await fetch_audit(engine, "auth.email_verified", user_id)
        assert len(audits) == 1, "a concurrent verify must not duplicate the success audit"

    async def test_token_for_a_soft_deleted_user_returns_safe_422(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email, deleted=True)
        token = await seed_verify_token(engine, user_id)
        response = await client.post(VERIFY, json={"token": token})
        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert token not in response.text
        user = await fetch_user(engine, email)
        assert user["email_verified_at"] is None
        (row,) = await fetch_email_tokens(engine, user_id)
        assert row["used_at"] is None, "a rejected verify must roll the consumption back"

    @pytest.mark.parametrize("bad_token", ["", "E" * 1000])
    async def test_invalid_token_shape_returns_the_canonical_validation_envelope(
        self, client, bad_token
    ):
        response = await client.post(VERIFY, json={"token": bad_token})
        error = assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert error["message_key"] == "errors.validationFailed"
        if bad_token:
            assert bad_token not in response.text

    async def test_email_verified_at_is_set_only_once(self, client, engine):
        email = unique_email()
        user_id = await seed_user(engine, email)
        first_token = await seed_verify_token(engine, user_id)
        assert (await client.post(VERIFY, json={"token": first_token})).status_code == 200
        first_stamp = (await fetch_user(engine, email))["email_verified_at"]
        assert first_stamp is not None

        second_token = await seed_verify_token(engine, user_id)
        assert (await client.post(VERIFY, json={"token": second_token})).status_code == 200
        assert (await fetch_user(engine, email))["email_verified_at"] == first_stamp
