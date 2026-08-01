"""Migration tests for revision 0002_users against real Postgres (Task B1, slice 2)."""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.models.user import UiLocale, UserRole

SENTINEL_TABLE = "b1_users_sentinel"


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


def _insert_user(database_url: str, **overrides):
    values = {
        "email": f"founder-{uuid.uuid4().hex}@example.com",
        "password_hash": "$argon2id$fake-for-migration-test",
        "full_name": "Test Founder",
        "role": "founder",
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO users ({columns}) VALUES ({placeholders}) "  # noqa: S608 - test-owned identifiers
                "RETURNING id, email, role, locale, email_verified_at, deleted_at, "
                "purge_after, created_at, updated_at"
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
                "FROM information_schema.columns WHERE table_name = 'users'"
            )
        )
        return {row["column_name"]: dict(row) for row in result.mappings()}

    return _db(database_url, fn)


def _enum_labels(database_url: str, type_name: str) -> list[str]:
    return _scalars(
        database_url,
        "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = :type_name ORDER BY e.enumsortorder",
        type_name=type_name,
    )


@pytest.fixture()
def db_at_0002(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0002_users")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


def test_upgrade_creates_citext_extension(db_at_0002):
    assert _scalars(db_at_0002, "SELECT extname FROM pg_extension WHERE extname = 'citext'")


def test_upgrade_creates_enum_types_matching_python_enums(db_at_0002):
    assert _enum_labels(db_at_0002, "user_role") == [r.value for r in UserRole] == ["founder", "vc"]
    assert _enum_labels(db_at_0002, "ui_locale") == [x.value for x in UiLocale] == ["uz", "ru"]


def test_users_columns_types_and_nullability(db_at_0002):
    cols = _column_info(db_at_0002)
    expected = {
        # name: (udt_name, nullable)
        "id": ("uuid", "NO"),
        "email": ("citext", "NO"),
        "password_hash": ("text", "NO"),
        "full_name": ("text", "NO"),
        "role": ("user_role", "NO"),
        "locale": ("ui_locale", "NO"),
        "email_verified_at": ("timestamptz", "YES"),
        "deleted_at": ("timestamptz", "YES"),
        "purge_after": ("timestamptz", "YES"),
        "created_at": ("timestamptz", "NO"),
        "updated_at": ("timestamptz", "NO"),
    }
    assert set(cols) == set(expected)
    for name, (udt, nullable) in expected.items():
        assert cols[name]["udt_name"] == udt, name
        assert cols[name]["is_nullable"] == nullable, name
    assert "gen_random_uuid()" in cols["id"]["column_default"]
    assert "uz" in cols["locale"]["column_default"]
    assert "now()" in cols["created_at"]["column_default"]
    assert "now()" in cols["updated_at"]["column_default"]


def test_users_primary_key_unique_email_and_partial_purge_index(db_at_0002):
    indexdefs = _scalars(db_at_0002, "SELECT indexdef FROM pg_indexes WHERE tablename = 'users'")
    assert any("users_pkey" in d and "(id)" in d for d in indexdefs)
    assert any("UNIQUE" in d and "(email)" in d for d in indexdefs)
    purge = [d for d in indexdefs if "ix_users_purge" in d]
    assert purge, "partial purge index missing"
    assert "(purge_after IS NOT NULL)" in purge[0]


def test_insert_applies_defaults(db_at_0002):
    row = _insert_user(db_at_0002)
    assert isinstance(row["id"], uuid.UUID)
    assert row["locale"] == "uz"
    assert row["email_verified_at"] is None
    assert row["deleted_at"] is None
    assert row["purge_after"] is None
    for stamp in (row["created_at"], row["updated_at"]):
        assert stamp.tzinfo is not None, "timestamps must be timezone-aware"
        assert abs((stamp - datetime.now(UTC)).total_seconds()) < 60


def test_email_uniqueness_is_case_insensitive_with_real_inserts(db_at_0002):
    email = f"Case-{uuid.uuid4().hex}@Example.COM"
    _insert_user(db_at_0002, email=email)
    with pytest.raises(IntegrityError):
        _insert_user(db_at_0002, email=email.lower())


def test_role_accepts_vc_and_rejects_unknown_labels(db_at_0002):
    assert _insert_user(db_at_0002, role="vc")["role"] == "vc"
    with pytest.raises(sa.exc.DBAPIError):
        _insert_user(db_at_0002, role="admin")


def test_downgrade_removes_users_and_enums_but_keeps_citext_and_unrelated_state(
    db_at_0002, alembic_config, run_alembic
):
    async def create_sentinel(conn):
        await conn.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {SENTINEL_TABLE} (id int)"))

    _db(db_at_0002, create_sentinel)
    try:
        run_alembic(command.downgrade, alembic_config, "0001_baseline")

        (users_reg,) = _scalars(db_at_0002, "SELECT to_regclass('public.users')")
        assert users_reg is None, "downgrade must drop the users table"
        assert not _scalars(
            db_at_0002,
            "SELECT typname FROM pg_type WHERE typname IN ('user_role', 'ui_locale')",
        ), "downgrade must drop the enum types"
        assert _scalars(db_at_0002, "SELECT extname FROM pg_extension WHERE extname = 'citext'"), (
            "downgrade must not drop the shared citext extension"
        )
        (sentinel,) = _scalars(db_at_0002, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0002, "SELECT version_num FROM alembic_version") == ["0001_baseline"]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")
        _db(
            db_at_0002,
            lambda conn: conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}")),
        )
