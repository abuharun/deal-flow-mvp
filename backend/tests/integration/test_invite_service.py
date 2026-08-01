"""create_invite against a real AsyncSession (Task B2, slice 1).

Transaction contract under test: the service flushes but never commits — the
caller (CLI/router, later) owns the transaction boundary.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
import sqlalchemy as sa

from app.db import build_engine, build_sessionmaker
from app.services.invite_service import create_invite

FROZEN_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
ACTIVATION_BASE = "https://bevosita.example.com"


def frozen_clock() -> datetime:
    return FROZEN_NOW


def _unique_email() -> str:
    return f"invitee-{uuid.uuid4().hex}@example.com"


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


async def _fetch_rows(conn_or_session, email: str) -> list[dict]:
    result = await conn_or_session.execute(
        sa.text(
            "SELECT email, token_hash, created_by, expires_at, used_at "
            "FROM invites WHERE email = :email"
        ),
        {"email": email},
    )
    return [dict(row) for row in result.mappings()]


async def test_create_invite_persists_row_with_injected_clock_and_label(session):
    email = _unique_email()
    grant = await create_invite(
        session,
        email=email,
        created_by="cli:admin",
        activation_base_url=ACTIVATION_BASE,
        clock=frozen_clock,
    )

    (row,) = await _fetch_rows(session, email)
    assert row["email"] == email
    assert row["created_by"] == "cli:admin"
    assert row["expires_at"] == FROZEN_NOW + timedelta(days=14), "default expiry is 14 days"
    assert row["used_at"] is None
    assert grant.invite.expires_at == FROZEN_NOW + timedelta(days=14)


async def test_raw_token_returned_once_and_db_stores_only_sha256(session):
    email = _unique_email()
    grant = await create_invite(
        session,
        email=email,
        created_by="cli:admin",
        activation_base_url=ACTIVATION_BASE,
        clock=frozen_clock,
    )

    parts = urlsplit(grant.activation_url)
    assert parse_qs(parts.query, strict_parsing=True) == {"token": [grant.token]}
    assert grant.activation_url.count(grant.token) == 1

    (row,) = await _fetch_rows(session, email)
    assert row["token_hash"] == hashlib.sha256(grant.token.encode("ascii")).digest()
    assert grant.token.encode("ascii") not in row["token_hash"], "plaintext must never be stored"
    for value in row.values():
        assert value != grant.token


async def test_duplicate_email_allowed_when_tokens_differ(session):
    email = _unique_email()
    kwargs = dict(created_by="cli:admin", activation_base_url=ACTIVATION_BASE, clock=frozen_clock)
    first = await create_invite(session, email=email, **kwargs)
    second = await create_invite(session, email=email, **kwargs)

    assert first.token != second.token
    assert len(await _fetch_rows(session, email)) == 2


async def test_duplicate_token_hash_rejected_even_for_different_emails(session):
    kwargs = dict(created_by="cli:admin", activation_base_url=ACTIVATION_BASE, clock=frozen_clock)
    await create_invite(session, email=_unique_email(), token_factory=lambda: "fixed", **kwargs)
    with pytest.raises(sa.exc.IntegrityError):
        await create_invite(session, email=_unique_email(), token_factory=lambda: "fixed", **kwargs)


async def test_email_keeps_citext_semantics(session):
    email = f"MiXeD-{uuid.uuid4().hex}@Example.COM"
    await create_invite(
        session,
        email=email,
        created_by="cli:admin",
        activation_base_url=ACTIVATION_BASE,
        clock=frozen_clock,
    )
    rows = await _fetch_rows(session, email.lower())
    assert [row["email"] for row in rows] == [email], "citext: case-insensitive match, case kept"


async def test_service_never_commits_rollback_discards_the_invite(engine, session):
    email = _unique_email()
    await create_invite(
        session,
        email=email,
        created_by="cli:admin",
        activation_base_url=ACTIVATION_BASE,
        clock=frozen_clock,
    )
    # Visible inside the caller's transaction (the row was flushed) ...
    assert len(await _fetch_rows(session, email)) == 1
    # ... invisible outside it before commit ...
    async with engine.connect() as conn:
        assert await _fetch_rows(conn, email) == []
    # ... and gone after the caller rolls back.
    await session.rollback()
    assert await _fetch_rows(session, email) == []
    async with engine.connect() as conn:
        assert await _fetch_rows(conn, email) == []
