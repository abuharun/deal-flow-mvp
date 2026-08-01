"""Migration tests for revision 0003_invites against real Postgres (Task B2, slice 1)."""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

SENTINEL_TABLE = "b2_invites_sentinel"


def _db(database_url: str, fn):
    async def go():
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as conn:
                return await fn(conn)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _scalars(database_url: str, query: str, **params) -> list:
    async def fn(conn):
        result = await conn.execute(sa.text(query), params)
        return list(result.scalars())

    return _db(database_url, fn)


def _insert_invite(database_url: str, **overrides):
    values = {
        "email": f"invitee-{uuid.uuid4().hex}@example.com",
        "token_hash": hashlib.sha256(uuid.uuid4().bytes).digest(),
        "created_by": "cli:test",
        "expires_at": datetime.now(UTC) + timedelta(days=14),
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO invites ({columns}) VALUES ({placeholders}) "  # noqa: S608 - test-owned identifiers
                "RETURNING id, email, token_hash, created_by, expires_at, used_at, created_at"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


def _column_info(database_url: str) -> dict[str, dict]:
    async def fn(conn):
        result = await conn.execute(
            sa.text(
                "SELECT column_name, udt_name, is_nullable, column_default "
                "FROM information_schema.columns WHERE table_name = 'invites'"
            )
        )
        return {row["column_name"]: dict(row) for row in result.mappings()}

    return _db(database_url, fn)


@pytest.fixture()
def db_at_0003(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0002_users")
    run_alembic(command.upgrade, alembic_config, "0003_invites")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


def test_invites_columns_types_nullability_and_defaults(db_at_0003):
    cols = _column_info(db_at_0003)
    expected = {
        # name: (udt_name, nullable)
        "id": ("uuid", "NO"),
        "email": ("citext", "NO"),
        "token_hash": ("bytea", "NO"),
        "created_by": ("text", "NO"),
        "expires_at": ("timestamptz", "NO"),
        "used_at": ("timestamptz", "YES"),
        "created_at": ("timestamptz", "NO"),
    }
    assert set(cols) == set(expected)
    for name, (udt, nullable) in expected.items():
        assert cols[name]["udt_name"] == udt, name
        assert cols[name]["is_nullable"] == nullable, name
    assert "gen_random_uuid()" in cols["id"]["column_default"]
    assert "now()" in cols["created_at"]["column_default"]


def test_invites_indexes_support_email_lookup_and_expiry_cleanup(db_at_0003):
    indexdefs = _scalars(db_at_0003, "SELECT indexdef FROM pg_indexes WHERE tablename = 'invites'")
    assert any("invites_pkey" in d and "(id)" in d for d in indexdefs)
    assert any("UNIQUE" in d and "(token_hash)" in d for d in indexdefs)
    assert any("(email)" in d and "UNIQUE" not in d for d in indexdefs), (
        "email lookups need a non-unique index (duplicate invites are allowed)"
    )
    assert any("(expires_at)" in d for d in indexdefs), "expiry cleanup needs an index"


def test_insert_applies_defaults(db_at_0003):
    row = _insert_invite(db_at_0003)
    assert isinstance(row["id"], uuid.UUID)
    assert row["used_at"] is None
    assert row["expires_at"].tzinfo is not None, "expires_at must be timezone-aware"
    assert row["created_at"].tzinfo is not None, "created_at must be timezone-aware"
    assert abs((row["created_at"] - datetime.now(UTC)).total_seconds()) < 60


def test_duplicate_token_hash_is_rejected(db_at_0003):
    token_hash = hashlib.sha256(uuid.uuid4().bytes).digest()
    _insert_invite(db_at_0003, token_hash=token_hash)
    with pytest.raises(IntegrityError):
        _insert_invite(db_at_0003, token_hash=token_hash)


def test_email_has_citext_semantics(db_at_0003):
    email = f"MiXeD-{uuid.uuid4().hex}@Example.COM"
    _insert_invite(db_at_0003, email=email)
    found = _scalars(
        db_at_0003, "SELECT email FROM invites WHERE email = :email", email=email.lower()
    )
    assert found == [email], "citext lookup must match case-insensitively, preserving case"


def test_downgrade_removes_invites_only_and_preserves_users_and_sentinel(
    db_at_0003, alembic_config, run_alembic
):
    user_email = f"survivor-{uuid.uuid4().hex}@example.com"

    async def seed(conn):
        await conn.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {SENTINEL_TABLE} (id int)"))
        await conn.execute(
            sa.text(
                "INSERT INTO users (email, password_hash, full_name, role) "
                "VALUES (:email, 'x', 'Survivor', 'founder')"
            ),
            {"email": user_email},
        )

    _db(db_at_0003, seed)
    try:
        run_alembic(command.downgrade, alembic_config, "0002_users")

        (invites_reg,) = _scalars(db_at_0003, "SELECT to_regclass('public.invites')")
        assert invites_reg is None, "downgrade must drop the invites table"
        assert _scalars(
            db_at_0003, "SELECT email FROM users WHERE email = :email", email=user_email
        ) == [user_email], "downgrade must preserve users"
        (sentinel,) = _scalars(db_at_0003, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0003, "SELECT version_num FROM alembic_version") == ["0002_users"]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")

        async def cleanup(conn):
            await conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}"))
            await conn.execute(
                sa.text("DELETE FROM users WHERE email = :email"), {"email": user_email}
            )

        _db(db_at_0003, cleanup)
