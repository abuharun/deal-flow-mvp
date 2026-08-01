"""create_email_token / consume_email_token against a real AsyncSession (Task B3, slice A).

Transaction contract under test: the service flushes but never commits — the
caller (verify endpoint, later) owns the transaction boundary. Issuing a new
token atomically marks any still-active token for the same user/purpose as
used, so only the newest token is ever usable.
"""

import dataclasses
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from app.db import build_engine, build_sessionmaker
from app.models.email_token import EmailTokenPurpose
from app.services.email_token_service import (
    DEFAULT_RESET_TTL,
    DEFAULT_VERIFY_TTL,
    EmailTokenConsumeOutcome,
    consume_email_token,
    create_email_token,
)

FROZEN_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
LATER = FROZEN_NOW + timedelta(minutes=5)
EVEN_LATER = FROZEN_NOW + timedelta(minutes=10)


def frozen_clock() -> datetime:
    return FROZEN_NOW


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def session(engine):
    # No commit anywhere in these tests: rollback on exit keeps the DB clean.
    async with build_sessionmaker(engine)() as session:
        yield session
        await session.rollback()


async def _create_user(session) -> uuid.UUID:
    result = await session.execute(
        sa.text(
            "INSERT INTO users (email, password_hash, full_name, role) "
            "VALUES (:email, 'x', 'Token Owner', 'founder') RETURNING id"
        ),
        {"email": f"owner-{uuid.uuid4().hex}@example.com"},
    )
    return result.scalar_one()


async def _fetch_rows(conn_or_session, user_id: uuid.UUID) -> list[dict]:
    result = await conn_or_session.execute(
        sa.text(
            "SELECT id, user_id, purpose, token_hash, expires_at, used_at "
            "FROM email_tokens WHERE user_id = :user_id ORDER BY expires_at"
        ),
        {"user_id": str(user_id)},
    )
    return [dict(row) for row in result.mappings()]


class TestCreateEmailToken:
    async def test_verify_purpose_defaults_to_24_hours(self, session):
        user_id = await _create_user(session)
        grant = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=frozen_clock
        )
        (row,) = await _fetch_rows(session, user_id)
        assert row["purpose"] == "verify"
        assert row["expires_at"] == FROZEN_NOW + timedelta(hours=24)
        assert row["used_at"] is None
        assert grant.email_token.expires_at == FROZEN_NOW + timedelta(hours=24)
        assert DEFAULT_VERIFY_TTL == timedelta(hours=24)

    async def test_reset_purpose_defaults_to_30_minutes(self, session):
        user_id = await _create_user(session)
        await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.RESET, clock=frozen_clock
        )
        (row,) = await _fetch_rows(session, user_id)
        assert row["purpose"] == "reset"
        assert row["expires_at"] == FROZEN_NOW + timedelta(minutes=30)
        assert DEFAULT_RESET_TTL == timedelta(minutes=30)

    async def test_explicit_expires_in_overrides_the_default(self, session):
        user_id = await _create_user(session)
        await create_email_token(
            session,
            user_id=user_id,
            purpose=EmailTokenPurpose.VERIFY,
            clock=frozen_clock,
            expires_in=timedelta(hours=1),
        )
        (row,) = await _fetch_rows(session, user_id)
        assert row["expires_at"] == FROZEN_NOW + timedelta(hours=1)

    async def test_raw_token_returned_once_in_frozen_grant_and_db_stores_only_sha256(self, session):
        user_id = await _create_user(session)
        grant = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=frozen_clock
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            grant.token = "tampered"

        (row,) = await _fetch_rows(session, user_id)
        assert row["token_hash"] == hashlib.sha256(grant.token.encode("ascii")).digest()
        assert grant.token.encode("ascii") not in row["token_hash"]
        for value in row.values():
            assert value != grant.token, "plaintext must never be stored"

    async def test_injected_token_factory_is_used(self, session):
        user_id = await _create_user(session)
        grant = await create_email_token(
            session,
            user_id=user_id,
            purpose=EmailTokenPurpose.VERIFY,
            clock=frozen_clock,
            token_factory=lambda: "fixed-token",
        )
        assert grant.token == "fixed-token"
        (row,) = await _fetch_rows(session, user_id)
        assert row["token_hash"] == hashlib.sha256(b"fixed-token").digest()

    async def test_new_token_marks_still_active_same_user_purpose_tokens_used(self, session):
        user_id = await _create_user(session)
        first = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=frozen_clock
        )
        second = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=lambda: LATER
        )

        rows = {row["id"]: row for row in await _fetch_rows(session, user_id)}
        assert rows[first.email_token.id]["used_at"] == LATER, "older token must be invalidated"
        assert rows[second.email_token.id]["used_at"] is None, "newest token must stay usable"

        outcome = await consume_email_token(
            session, token=first.token, purpose=EmailTokenPurpose.VERIFY, clock=lambda: LATER
        )
        assert outcome.outcome is EmailTokenConsumeOutcome.USED

    async def test_invalidation_does_not_restamp_already_used_tokens(self, session):
        user_id = await _create_user(session)
        first = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=frozen_clock
        )
        await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=lambda: LATER
        )
        await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=lambda: EVEN_LATER
        )
        rows = {row["id"]: row for row in await _fetch_rows(session, user_id)}
        assert rows[first.email_token.id]["used_at"] == LATER, (
            "an already-used token must keep its original used_at"
        )

    async def test_invalidation_is_scoped_to_the_same_user_and_purpose(self, session):
        user_id = await _create_user(session)
        other_user_id = await _create_user(session)
        reset = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.RESET, clock=frozen_clock
        )
        other = await create_email_token(
            session, user_id=other_user_id, purpose=EmailTokenPurpose.VERIFY, clock=frozen_clock
        )
        await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=lambda: LATER
        )

        (reset_row,) = [
            r for r in await _fetch_rows(session, user_id) if r["id"] == reset.email_token.id
        ]
        assert reset_row["used_at"] is None, "other purposes must be untouched"
        (other_row,) = await _fetch_rows(session, other_user_id)
        assert other_row["id"] == other.email_token.id
        assert other_row["used_at"] is None, "other users must be untouched"

    async def test_service_never_commits_rollback_discards_the_token(self, engine, session):
        user_id = await _create_user(session)
        await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=frozen_clock
        )
        # Visible inside the caller's transaction (the row was flushed) ...
        assert len(await _fetch_rows(session, user_id)) == 1
        # ... invisible outside it before commit ...
        async with engine.connect() as conn:
            assert await _fetch_rows(conn, user_id) == []
        # ... and gone after the caller rolls back.
        await session.rollback()
        async with engine.connect() as conn:
            assert await _fetch_rows(conn, user_id) == []


class TestConsumeEmailToken:
    async def test_active_token_is_consumed_and_marked_used(self, session):
        user_id = await _create_user(session)
        grant = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=frozen_clock
        )
        result = await consume_email_token(
            session, token=grant.token, purpose=EmailTokenPurpose.VERIFY, clock=lambda: LATER
        )
        assert result.outcome is EmailTokenConsumeOutcome.CONSUMED
        assert result.email_token is not None
        assert result.email_token.user_id == user_id
        (row,) = await _fetch_rows(session, user_id)
        assert row["used_at"] == LATER

    async def test_consumed_token_cannot_be_consumed_twice(self, session):
        user_id = await _create_user(session)
        grant = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=frozen_clock
        )
        first = await consume_email_token(
            session, token=grant.token, purpose=EmailTokenPurpose.VERIFY, clock=lambda: LATER
        )
        assert first.outcome is EmailTokenConsumeOutcome.CONSUMED
        second = await consume_email_token(
            session, token=grant.token, purpose=EmailTokenPurpose.VERIFY, clock=lambda: LATER
        )
        assert second.outcome is EmailTokenConsumeOutcome.USED
        assert second.email_token is None

    async def test_unknown_token_reports_unknown(self, session):
        result = await consume_email_token(
            session, token="never-issued", purpose=EmailTokenPurpose.VERIFY, clock=frozen_clock
        )
        assert result.outcome is EmailTokenConsumeOutcome.UNKNOWN
        assert result.email_token is None

    async def test_purpose_mismatch_reports_unknown(self, session):
        user_id = await _create_user(session)
        grant = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=frozen_clock
        )
        result = await consume_email_token(
            session, token=grant.token, purpose=EmailTokenPurpose.RESET, clock=frozen_clock
        )
        assert result.outcome is EmailTokenConsumeOutcome.UNKNOWN

    async def test_expired_token_reports_expired_and_stays_unused(self, session):
        user_id = await _create_user(session)
        grant = await create_email_token(
            session, user_id=user_id, purpose=EmailTokenPurpose.VERIFY, clock=frozen_clock
        )
        result = await consume_email_token(
            session,
            token=grant.token,
            purpose=EmailTokenPurpose.VERIFY,
            clock=lambda: FROZEN_NOW + timedelta(hours=25),
        )
        assert result.outcome is EmailTokenConsumeOutcome.EXPIRED
        assert result.email_token is None
        (row,) = await _fetch_rows(session, user_id)
        assert row["used_at"] is None, "an expired token must not be stamped used"
