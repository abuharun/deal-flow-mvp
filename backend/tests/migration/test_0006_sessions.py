"""Migration tests for revision 0006_auth_sessions against real Postgres (Task B4, slice A).

auth_sessions holds only SHA-256 digests of refresh tokens. Rows form rotation
families (family_id) sharing one absolute expiry, tied to a user with
ON DELETE CASCADE so account deletion leaves no dangling sessions.
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

SENTINEL_TABLE = "b4_sessions_sentinel"


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


def _column_info(database_url: str) -> dict[str, dict]:
    async def fn(conn):
        result = await conn.execute(
            sa.text(
                "SELECT column_name, udt_name, is_nullable, column_default "
                "FROM information_schema.columns WHERE table_name = 'auth_sessions'"
            )
        )
        return {row["column_name"]: dict(row) for row in result.mappings()}

    return _db(database_url, fn)


def _insert_user(database_url: str) -> uuid.UUID:
    email = f"sessions-{uuid.uuid4().hex}@example.com"

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                "INSERT INTO users (email, password_hash, full_name, role) "
                "VALUES (:email, 'x', 'Session Owner', 'founder') RETURNING id"
            ),
            {"email": email},
        )
        return result.scalar_one()

    return _db(database_url, fn)


def _insert_session(database_url: str, user_id: uuid.UUID, **overrides):
    values = {
        "user_id": str(user_id),
        "family_id": str(uuid.uuid4()),
        "token_hash": uuid.uuid4().bytes + uuid.uuid4().bytes,
    }
    values.update(overrides)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                "INSERT INTO auth_sessions (user_id, family_id, token_hash, expires_at) "
                "VALUES (:user_id, :family_id, :token_hash, now() + interval '30 days') "
                "RETURNING id, user_id, family_id, token_hash, expires_at, rotated_at, "
                "revoked_at, user_agent, created_at"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


@pytest.fixture()
def db_at_0006(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0005_email_tokens")
    run_alembic(command.upgrade, alembic_config, "0006_auth_sessions")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


def test_auth_sessions_columns_types_nullability_and_defaults(db_at_0006):
    cols = _column_info(db_at_0006)
    expected = {
        # name: (udt_name, nullable)
        "id": ("uuid", "NO"),
        "user_id": ("uuid", "NO"),
        "family_id": ("uuid", "NO"),
        "token_hash": ("bytea", "NO"),
        "expires_at": ("timestamptz", "NO"),
        "rotated_at": ("timestamptz", "YES"),
        "revoked_at": ("timestamptz", "YES"),
        "user_agent": ("text", "YES"),
        "created_at": ("timestamptz", "NO"),
    }
    assert set(cols) == set(expected)
    for name, (udt, nullable) in expected.items():
        assert cols[name]["udt_name"] == udt, name
        assert cols[name]["is_nullable"] == nullable, name
    assert "gen_random_uuid()" in cols["id"]["column_default"]
    assert "now()" in cols["created_at"]["column_default"]


def test_indexes_support_user_family_lookup_and_expiry_sweeps(db_at_0006):
    indexdefs = _scalars(
        db_at_0006, "SELECT indexdef FROM pg_indexes WHERE tablename = 'auth_sessions'"
    )
    assert any("auth_sessions_pkey" in d and "(id)" in d for d in indexdefs)
    assert any("ix_sessions_user" in d and "(user_id)" in d for d in indexdefs)
    assert any("ix_sessions_family" in d and "(family_id)" in d for d in indexdefs)
    assert any("ix_sessions_expires_at" in d and "(expires_at)" in d for d in indexdefs)


def test_token_hash_is_unique(db_at_0006):
    user_id = _insert_user(db_at_0006)
    digest = uuid.uuid4().bytes + uuid.uuid4().bytes
    _insert_session(db_at_0006, user_id, token_hash=digest)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_session(db_at_0006, user_id, token_hash=digest)


def test_user_id_is_a_foreign_key_with_on_delete_cascade(db_at_0006):
    deltypes = _scalars(
        db_at_0006,
        "SELECT confdeltype::text FROM pg_constraint "
        "WHERE conrelid = 'auth_sessions'::regclass AND contype = 'f'",
    )
    assert deltypes == ["c"], "user_id FK must be ON DELETE CASCADE"

    user_id = _insert_user(db_at_0006)
    row = _insert_session(db_at_0006, user_id)
    _db(
        db_at_0006,
        lambda conn: conn.execute(
            sa.text("DELETE FROM users WHERE id = :id"), {"id": str(user_id)}
        ),
    )
    assert _scalars(
        db_at_0006, "SELECT count(*) FROM auth_sessions WHERE id = :id", id=row["id"]
    ) == [0], "deleting a user must cascade-delete their sessions"


def test_insert_without_user_is_rejected(db_at_0006):
    with pytest.raises(sa.exc.IntegrityError):
        _insert_session(db_at_0006, uuid.uuid4())


def test_insert_applies_defaults(db_at_0006):
    user_id = _insert_user(db_at_0006)
    row = _insert_session(db_at_0006, user_id)
    assert isinstance(row["id"], uuid.UUID)
    assert row["rotated_at"] is None
    assert row["revoked_at"] is None
    assert row["user_agent"] is None
    assert row["created_at"].tzinfo is not None, "created_at must be timezone-aware"
    assert row["expires_at"].tzinfo is not None, "expires_at must be timezone-aware"


def test_downgrade_removes_auth_sessions_and_preserves_everything_else(
    db_at_0006, alembic_config, run_alembic
):
    user_id = _insert_user(db_at_0006)
    _insert_session(db_at_0006, user_id)
    invite_email = f"survivor-invite-{uuid.uuid4().hex}@example.com"

    async def seed(conn):
        await conn.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {SENTINEL_TABLE} (id int)"))
        await conn.execute(
            sa.text(
                "INSERT INTO invites (email, token_hash, created_by, expires_at) "
                "VALUES (:email, :token_hash, 'cli:test', now() + interval '14 days')"
            ),
            {"email": invite_email, "token_hash": uuid.uuid4().bytes},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO email_tokens (user_id, purpose, token_hash, expires_at) "
                "VALUES (:user_id, 'verify', :token_hash, now() + interval '24 hours')"
            ),
            {"user_id": str(user_id), "token_hash": uuid.uuid4().bytes + uuid.uuid4().bytes},
        )
        # audit_log is append-only by design: inserted rows stay behind.
        await conn.execute(
            sa.text(
                "INSERT INTO audit_log (actor_type, action, entity_type) "
                "VALUES ('system', 'migration.test', 'user')"
            )
        )

    _db(db_at_0006, seed)
    try:
        run_alembic(command.downgrade, alembic_config, "0005_email_tokens")

        (sessions_reg,) = _scalars(db_at_0006, "SELECT to_regclass('public.auth_sessions')")
        assert sessions_reg is None, "downgrade must drop the auth_sessions table"

        assert _scalars(
            db_at_0006, "SELECT count(*) FROM users WHERE id = :id", id=str(user_id)
        ) == [1], "downgrade must preserve users"
        assert _scalars(
            db_at_0006, "SELECT count(*) FROM email_tokens WHERE user_id = :id", id=str(user_id)
        ) == [1], "downgrade must preserve email tokens"
        assert _scalars(
            db_at_0006, "SELECT email FROM invites WHERE email = :email", email=invite_email
        ) == [invite_email], "downgrade must preserve invites"
        assert (
            _scalars(
                db_at_0006,
                "SELECT count(*) FROM audit_log WHERE action = 'migration.test'",
            )[0]
            >= 1
        ), "downgrade must preserve the audit trail"
        (sentinel,) = _scalars(db_at_0006, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0006, "SELECT version_num FROM alembic_version") == [
            "0005_email_tokens"
        ]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")

        async def cleanup(conn):
            await conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}"))
            await conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": str(user_id)})
            await conn.execute(
                sa.text("DELETE FROM invites WHERE email = :email"), {"email": invite_email}
            )

        _db(db_at_0006, cleanup)
