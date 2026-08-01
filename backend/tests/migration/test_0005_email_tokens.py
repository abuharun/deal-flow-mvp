"""Migration tests for revision 0005_email_tokens against real Postgres (Task B3, slice A).

email_tokens holds only SHA-256 digests of verification/reset tokens, tied to a
user with ON DELETE CASCADE so account deletion leaves no dangling secrets.
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

SENTINEL_TABLE = "b3_email_tokens_sentinel"


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
                "FROM information_schema.columns WHERE table_name = 'email_tokens'"
            )
        )
        return {row["column_name"]: dict(row) for row in result.mappings()}

    return _db(database_url, fn)


def _insert_user(database_url: str) -> uuid.UUID:
    email = f"tokens-{uuid.uuid4().hex}@example.com"

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                "INSERT INTO users (email, password_hash, full_name, role) "
                "VALUES (:email, 'x', 'Token Owner', 'founder') RETURNING id"
            ),
            {"email": email},
        )
        return result.scalar_one()

    return _db(database_url, fn)


def _insert_token(database_url: str, user_id: uuid.UUID, **overrides):
    values = {
        "user_id": str(user_id),
        "purpose": "verify",
        "token_hash": uuid.uuid4().bytes + uuid.uuid4().bytes,
        "expires_at": None,
    }
    values.update(overrides)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                "INSERT INTO email_tokens (user_id, purpose, token_hash, expires_at) "
                "VALUES (:user_id, :purpose, :token_hash, "
                "coalesce(:expires_at, now() + interval '24 hours')) "
                "RETURNING id, user_id, purpose, token_hash, expires_at, used_at, created_at"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


@pytest.fixture()
def db_at_0005(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0004_audit_log")
    run_alembic(command.upgrade, alembic_config, "0005_email_tokens")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


def test_email_tokens_columns_types_nullability_and_defaults(db_at_0005):
    cols = _column_info(db_at_0005)
    expected = {
        # name: (udt_name, nullable)
        "id": ("uuid", "NO"),
        "user_id": ("uuid", "NO"),
        "purpose": ("email_token_purpose", "NO"),
        "token_hash": ("bytea", "NO"),
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


def test_email_token_purpose_enum_has_exactly_the_planned_values(db_at_0005):
    labels = _scalars(
        db_at_0005,
        "SELECT e.enumlabel FROM pg_enum e "
        "JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = 'email_token_purpose' ORDER BY e.enumsortorder",
    )
    assert labels == ["verify", "reset"]


def test_indexes_support_user_purpose_lookup_and_expiry_sweeps(db_at_0005):
    indexdefs = _scalars(
        db_at_0005, "SELECT indexdef FROM pg_indexes WHERE tablename = 'email_tokens'"
    )
    assert any("email_tokens_pkey" in d and "(id)" in d for d in indexdefs)
    assert any("ix_email_tokens_user_purpose" in d and "(user_id, purpose)" in d for d in indexdefs)
    assert any("ix_email_tokens_expires_at" in d and "(expires_at)" in d for d in indexdefs)


def test_token_hash_is_unique(db_at_0005):
    user_id = _insert_user(db_at_0005)
    digest = uuid.uuid4().bytes + uuid.uuid4().bytes
    _insert_token(db_at_0005, user_id, token_hash=digest)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_token(db_at_0005, user_id, token_hash=digest, purpose="reset")


def test_user_id_is_a_foreign_key_with_on_delete_cascade(db_at_0005):
    deltypes = _scalars(
        db_at_0005,
        "SELECT confdeltype::text FROM pg_constraint "
        "WHERE conrelid = 'email_tokens'::regclass AND contype = 'f'",
    )
    assert deltypes == ["c"], "user_id FK must be ON DELETE CASCADE"

    user_id = _insert_user(db_at_0005)
    row = _insert_token(db_at_0005, user_id)
    _db(
        db_at_0005,
        lambda conn: conn.execute(
            sa.text("DELETE FROM users WHERE id = :id"), {"id": str(user_id)}
        ),
    )
    assert _scalars(
        db_at_0005, "SELECT count(*) FROM email_tokens WHERE id = :id", id=row["id"]
    ) == [0], "deleting a user must cascade-delete their email tokens"


def test_insert_without_user_is_rejected(db_at_0005):
    with pytest.raises(sa.exc.IntegrityError):
        _insert_token(db_at_0005, uuid.uuid4())


def test_insert_applies_defaults(db_at_0005):
    user_id = _insert_user(db_at_0005)
    row = _insert_token(db_at_0005, user_id)
    assert isinstance(row["id"], uuid.UUID)
    assert row["used_at"] is None
    assert row["created_at"].tzinfo is not None, "created_at must be timezone-aware"
    assert row["expires_at"].tzinfo is not None, "expires_at must be timezone-aware"


def test_downgrade_removes_email_token_objects_and_preserves_everything_else(
    db_at_0005, alembic_config, run_alembic
):
    user_id = _insert_user(db_at_0005)
    _insert_token(db_at_0005, user_id)
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
        # audit_log is append-only by design: inserted rows stay behind.
        await conn.execute(
            sa.text(
                "INSERT INTO audit_log (actor_type, action, entity_type) "
                "VALUES ('system', 'migration.test', 'user')"
            )
        )

    _db(db_at_0005, seed)
    try:
        run_alembic(command.downgrade, alembic_config, "0004_audit_log")

        (tokens_reg,) = _scalars(db_at_0005, "SELECT to_regclass('public.email_tokens')")
        assert tokens_reg is None, "downgrade must drop the email_tokens table"
        assert _scalars(
            db_at_0005,
            "SELECT count(*) FROM pg_type WHERE typname = 'email_token_purpose'",
        ) == [0], "downgrade must drop the email_token_purpose enum"

        assert _scalars(
            db_at_0005, "SELECT count(*) FROM users WHERE id = :id", id=str(user_id)
        ) == [1], "downgrade must preserve users"
        assert _scalars(
            db_at_0005, "SELECT email FROM invites WHERE email = :email", email=invite_email
        ) == [invite_email], "downgrade must preserve invites"
        assert (
            _scalars(
                db_at_0005,
                "SELECT count(*) FROM audit_log WHERE action = 'migration.test'",
            )[0]
            >= 1
        ), "downgrade must preserve the audit trail"
        assert _scalars(
            db_at_0005, "SELECT count(*) FROM pg_extension WHERE extname = 'citext'"
        ) == [1], "downgrade must not touch the citext extension"
        (sentinel,) = _scalars(db_at_0005, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0005, "SELECT version_num FROM alembic_version") == ["0004_audit_log"]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")

        async def cleanup(conn):
            await conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}"))
            await conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": str(user_id)})
            await conn.execute(
                sa.text("DELETE FROM invites WHERE email = :email"), {"email": invite_email}
            )

        _db(db_at_0005, cleanup)
