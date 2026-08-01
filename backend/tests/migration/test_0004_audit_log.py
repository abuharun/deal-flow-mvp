"""Migration tests for revision 0004_audit_log against real Postgres (Task B2, slice 2).

The audit trail is only trustworthy if the database itself refuses mutation:
REVOKE alone does not bind the table owner, so a trigger must reject UPDATE
and DELETE regardless of who is connected.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

SENTINEL_TABLE = "b2_audit_sentinel"


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


def _insert_audit(database_url: str, **overrides):
    values = {
        "actor_type": "cli",
        "action": "cli.create_invite",
        "entity_type": "invite",
        "entity_id": str(uuid.uuid4()),
        "metadata": json.dumps({"email": f"a-{uuid.uuid4().hex}@example.com"}),
        "ip": "203.0.113.7",
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO audit_log ({columns}) VALUES ({placeholders}) "  # noqa: S608 - test-owned identifiers
                "RETURNING id, at, actor_type, actor_id, action, "
                "entity_type, entity_id, metadata, ip"
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
                "FROM information_schema.columns WHERE table_name = 'audit_log'"
            )
        )
        return {row["column_name"]: dict(row) for row in result.mappings()}

    return _db(database_url, fn)


@pytest.fixture()
def db_at_0004(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0003_invites")
    run_alembic(command.upgrade, alembic_config, "0004_audit_log")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


def test_audit_log_columns_types_nullability_and_defaults(db_at_0004):
    cols = _column_info(db_at_0004)
    expected = {
        # name: (udt_name, nullable)
        "id": ("uuid", "NO"),
        "at": ("timestamptz", "NO"),
        "actor_type": ("audit_actor_type", "NO"),
        "actor_id": ("uuid", "YES"),
        "action": ("text", "NO"),
        "entity_type": ("text", "NO"),
        "entity_id": ("uuid", "YES"),
        "metadata": ("jsonb", "NO"),
        "ip": ("inet", "YES"),
    }
    assert set(cols) == set(expected)
    for name, (udt, nullable) in expected.items():
        assert cols[name]["udt_name"] == udt, name
        assert cols[name]["is_nullable"] == nullable, name
    assert "gen_random_uuid()" in cols["id"]["column_default"]
    assert "now()" in cols["at"]["column_default"]
    assert "{}" in cols["metadata"]["column_default"], "metadata must default to empty jsonb"


def test_audit_actor_type_enum_has_exactly_the_planned_values(db_at_0004):
    labels = _scalars(
        db_at_0004,
        "SELECT e.enumlabel FROM pg_enum e "
        "JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = 'audit_actor_type' ORDER BY e.enumsortorder",
    )
    assert labels == ["user", "cli", "worker", "system"]


def test_audit_log_indexes_support_time_and_entity_lookups(db_at_0004):
    indexdefs = _scalars(
        db_at_0004, "SELECT indexdef FROM pg_indexes WHERE tablename = 'audit_log'"
    )
    assert any("audit_log_pkey" in d and "(id)" in d for d in indexdefs)
    assert any("ix_audit_at" in d and "(at)" in d for d in indexdefs)
    assert any("ix_audit_entity" in d and "(entity_type, entity_id)" in d for d in indexdefs)


def test_insert_applies_defaults(db_at_0004):
    async def fn(conn):
        result = await conn.execute(
            sa.text(
                "INSERT INTO audit_log (actor_type, action, entity_type) "
                "VALUES ('system', 'retention.purge', 'user') "
                "RETURNING id, at, actor_id, entity_id, metadata, ip"
            )
        )
        return result.mappings().one()

    row = _db(db_at_0004, fn)
    assert isinstance(row["id"], uuid.UUID)
    assert row["at"].tzinfo is not None, "at must be timezone-aware"
    assert abs((row["at"] - datetime.now(UTC)).total_seconds()) < 60
    assert row["actor_id"] is None
    assert row["entity_id"] is None
    metadata = row["metadata"]
    if isinstance(metadata, str):  # asyncpg returns jsonb as its text form
        metadata = json.loads(metadata)
    assert metadata == {}
    assert row["ip"] is None


def test_update_is_rejected_by_trigger(db_at_0004):
    row = _insert_audit(db_at_0004)
    with pytest.raises(sa.exc.DBAPIError, match="append-only"):
        _db(
            db_at_0004,
            lambda conn: conn.execute(
                sa.text("UPDATE audit_log SET action = 'tampered.rewrite' WHERE id = :id"),
                {"id": row["id"]},
            ),
        )
    # The row is untouched — the failed statement's transaction rolled back.
    assert _scalars(db_at_0004, "SELECT action FROM audit_log WHERE id = :id", id=row["id"]) == [
        row["action"]
    ]


def test_delete_is_rejected_by_trigger(db_at_0004):
    row = _insert_audit(db_at_0004)
    with pytest.raises(sa.exc.DBAPIError, match="append-only"):
        _db(
            db_at_0004,
            lambda conn: conn.execute(
                sa.text("DELETE FROM audit_log WHERE id = :id"), {"id": row["id"]}
            ),
        )
    assert _scalars(db_at_0004, "SELECT count(*) FROM audit_log WHERE id = :id", id=row["id"]) == [
        1
    ]


def test_downgrade_removes_audit_objects_and_preserves_everything_else(
    db_at_0004, alembic_config, run_alembic
):
    user_email = f"survivor-{uuid.uuid4().hex}@example.com"
    invite_email = f"survivor-invite-{uuid.uuid4().hex}@example.com"

    async def seed(conn):
        await conn.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {SENTINEL_TABLE} (id int)"))
        await conn.execute(
            sa.text(
                "INSERT INTO users (email, password_hash, full_name, role) "
                "VALUES (:email, 'x', 'Survivor', 'founder')"
            ),
            {"email": user_email},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO invites (email, token_hash, created_by, expires_at) "
                "VALUES (:email, :token_hash, 'cli:test', now() + interval '14 days')"
            ),
            {"email": invite_email, "token_hash": uuid.uuid4().bytes},
        )

    _db(db_at_0004, seed)
    try:
        run_alembic(command.downgrade, alembic_config, "0003_invites")

        (audit_reg,) = _scalars(db_at_0004, "SELECT to_regclass('public.audit_log')")
        assert audit_reg is None, "downgrade must drop the audit_log table"
        assert _scalars(
            db_at_0004,
            "SELECT count(*) FROM pg_type WHERE typname = 'audit_actor_type'",
        ) == [0], "downgrade must drop the audit_actor_type enum"
        assert _scalars(
            db_at_0004,
            "SELECT count(*) FROM pg_proc WHERE proname LIKE '%audit%'",
        ) == [0], "downgrade must drop the append-only trigger function"

        assert _scalars(
            db_at_0004, "SELECT email FROM users WHERE email = :email", email=user_email
        ) == [user_email], "downgrade must preserve users"
        assert _scalars(
            db_at_0004, "SELECT email FROM invites WHERE email = :email", email=invite_email
        ) == [invite_email], "downgrade must preserve invites"
        assert _scalars(
            db_at_0004, "SELECT count(*) FROM pg_extension WHERE extname = 'citext'"
        ) == [1], "downgrade must not touch the citext extension"
        (sentinel,) = _scalars(db_at_0004, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0004, "SELECT version_num FROM alembic_version") == ["0003_invites"]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")

        async def cleanup(conn):
            await conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}"))
            await conn.execute(
                sa.text("DELETE FROM users WHERE email = :email"), {"email": user_email}
            )
            await conn.execute(
                sa.text("DELETE FROM invites WHERE email = :email"), {"email": invite_email}
            )

        _db(db_at_0004, cleanup)
