"""Migration tests for revision 0007_startups against real Postgres.

startups is founder-owned (many startups per founder — founder_id is indexed
but NEVER unique) with a lifecycle status enum and a monotonically increasing
input_revision. submissions is the one-to-one founder questionnaire keyed by a
UNIQUE startup_id FK with ON DELETE CASCADE. Downgrade must remove exactly
these objects and leave every auth-era table (users, auth_sessions, invites,
email_tokens, audit_log) untouched.
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

SENTINEL_TABLE = "b6_startups_sentinel"

STARTUP_STATUSES = ["draft", "submitted", "analyzing", "report_ready", "vc_visible"]


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


def _column_info(database_url: str, table: str) -> dict[str, dict]:
    async def fn(conn):
        result = await conn.execute(
            sa.text(
                "SELECT column_name, udt_name, is_nullable, column_default "
                "FROM information_schema.columns WHERE table_name = :table"
            ),
            {"table": table},
        )
        return {row["column_name"]: dict(row) for row in result.mappings()}

    return _db(database_url, fn)


def _insert_founder(database_url: str) -> uuid.UUID:
    email = f"startups-{uuid.uuid4().hex}@example.com"

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                "INSERT INTO users (email, password_hash, full_name, role) "
                "VALUES (:email, 'x', 'Startup Owner', 'founder') RETURNING id"
            ),
            {"email": email},
        )
        return result.scalar_one()

    return _db(database_url, fn)


def _insert_startup(database_url: str, founder_id: uuid.UUID, **overrides):
    values = {"founder_id": str(founder_id), "name": f"Startup {uuid.uuid4().hex[:8]}"}
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO startups ({columns}) VALUES ({placeholders}) "
                "RETURNING id, founder_id, name, one_liner, sector, funding_stage, city, "
                "status, input_revision, submitted_at, vc_visible_at, created_at, updated_at"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


def _insert_submission(database_url: str, startup_id: uuid.UUID, **overrides):
    values = {"startup_id": str(startup_id)}
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO submissions ({columns}) VALUES ({placeholders}) "
                "RETURNING id, startup_id, problem, product, market, traction, team, ask, "
                "revenue, growth, ask_amount, dataroom_url, completed_steps, updated_at"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


@pytest.fixture()
def db_at_0007(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0006_auth_sessions")
    run_alembic(command.upgrade, alembic_config, "0007_startups")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


def test_startups_columns_types_nullability_and_defaults(db_at_0007):
    cols = _column_info(db_at_0007, "startups")
    expected = {
        # name: (udt_name, nullable)
        "id": ("uuid", "NO"),
        "founder_id": ("uuid", "NO"),
        "name": ("text", "NO"),
        "one_liner": ("text", "NO"),
        "sector": ("text", "NO"),
        "funding_stage": ("text", "NO"),
        "city": ("text", "NO"),
        "status": ("startup_status", "NO"),
        "input_revision": ("int4", "NO"),
        "submitted_at": ("timestamptz", "YES"),
        "vc_visible_at": ("timestamptz", "YES"),
        "created_at": ("timestamptz", "NO"),
        "updated_at": ("timestamptz", "NO"),
    }
    assert set(cols) == set(expected)
    for name, (udt, nullable) in expected.items():
        assert cols[name]["udt_name"] == udt, name
        assert cols[name]["is_nullable"] == nullable, name
    assert "gen_random_uuid()" in cols["id"]["column_default"]
    assert "draft" in cols["status"]["column_default"]
    assert cols["input_revision"]["column_default"] == "1"
    assert "now()" in cols["created_at"]["column_default"]
    assert "now()" in cols["updated_at"]["column_default"]


def test_submissions_columns_types_nullability_and_defaults(db_at_0007):
    cols = _column_info(db_at_0007, "submissions")
    expected = {
        "id": ("uuid", "NO"),
        "startup_id": ("uuid", "NO"),
        "problem": ("text", "NO"),
        "product": ("text", "NO"),
        "market": ("text", "NO"),
        "traction": ("text", "NO"),
        "team": ("text", "NO"),
        "ask": ("text", "NO"),
        "revenue": ("text", "YES"),
        "growth": ("text", "YES"),
        "ask_amount": ("int8", "YES"),
        "dataroom_url": ("text", "YES"),
        "completed_steps": ("_text", "NO"),
        "updated_at": ("timestamptz", "NO"),
    }
    assert set(cols) == set(expected)
    for name, (udt, nullable) in expected.items():
        assert cols[name]["udt_name"] == udt, name
        assert cols[name]["is_nullable"] == nullable, name
    for answer in ("problem", "product", "market", "traction", "team", "ask"):
        assert "''" in cols[answer]["column_default"], answer
    assert "{}" in cols["completed_steps"]["column_default"]


def test_startup_status_enum_has_exactly_the_lifecycle_values(db_at_0007):
    values = _scalars(
        db_at_0007,
        "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = 'startup_status' ORDER BY e.enumsortorder",
    )
    assert values == STARTUP_STATUSES


def test_founder_id_is_indexed_but_never_unique(db_at_0007):
    indexdefs = _scalars(db_at_0007, "SELECT indexdef FROM pg_indexes WHERE tablename = 'startups'")
    founder_indexes = [d for d in indexdefs if "founder_id" in d]
    assert founder_indexes, "founder_id must be indexed for per-founder listing"
    assert all("UNIQUE" not in d.upper() for d in founder_indexes), (
        "a founder owns MULTIPLE startups; founder_id must never be unique"
    )

    # Behavioral proof: one founder can own several startups.
    founder_id = _insert_founder(db_at_0007)
    first = _insert_startup(db_at_0007, founder_id)
    second = _insert_startup(db_at_0007, founder_id)
    assert first["id"] != second["id"]


def test_startup_id_is_unique_one_submission_per_startup(db_at_0007):
    founder_id = _insert_founder(db_at_0007)
    startup = _insert_startup(db_at_0007, founder_id)
    _insert_submission(db_at_0007, startup["id"])
    with pytest.raises(sa.exc.IntegrityError):
        _insert_submission(db_at_0007, startup["id"])


def test_foreign_keys_cascade_user_to_startup_to_submission(db_at_0007):
    for table in ("startups", "submissions"):
        deltypes = _scalars(
            db_at_0007,
            f"SELECT confdeltype::text FROM pg_constraint "
            f"WHERE conrelid = '{table}'::regclass AND contype = 'f'",
        )
        assert deltypes == ["c"], f"{table} FK must be ON DELETE CASCADE"

    founder_id = _insert_founder(db_at_0007)
    startup = _insert_startup(db_at_0007, founder_id)
    submission = _insert_submission(db_at_0007, startup["id"])
    _db(
        db_at_0007,
        lambda conn: conn.execute(
            sa.text("DELETE FROM users WHERE id = :id"), {"id": str(founder_id)}
        ),
    )
    assert _scalars(
        db_at_0007, "SELECT count(*) FROM startups WHERE id = :id", id=startup["id"]
    ) == [0]
    assert _scalars(
        db_at_0007, "SELECT count(*) FROM submissions WHERE id = :id", id=submission["id"]
    ) == [0]


def test_insert_applies_draft_defaults(db_at_0007):
    founder_id = _insert_founder(db_at_0007)
    startup = _insert_startup(db_at_0007, founder_id)
    assert isinstance(startup["id"], uuid.UUID)
    assert startup["status"] == "draft"
    assert startup["input_revision"] == 1
    assert startup["one_liner"] == ""
    assert startup["submitted_at"] is None
    assert startup["vc_visible_at"] is None
    assert startup["created_at"].tzinfo is not None

    submission = _insert_submission(db_at_0007, startup["id"])
    assert submission["problem"] == ""
    assert submission["ask"] == ""
    assert submission["revenue"] is None
    assert submission["ask_amount"] is None
    assert submission["dataroom_url"] is None
    assert submission["completed_steps"] == []
    assert submission["updated_at"].tzinfo is not None


def test_input_revision_below_one_is_rejected(db_at_0007):
    founder_id = _insert_founder(db_at_0007)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_startup(db_at_0007, founder_id, input_revision=0)


def test_negative_ask_amount_is_rejected(db_at_0007):
    founder_id = _insert_founder(db_at_0007)
    startup = _insert_startup(db_at_0007, founder_id)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_submission(db_at_0007, startup["id"], ask_amount=-1)


def test_orphan_startup_and_submission_are_rejected(db_at_0007):
    with pytest.raises(sa.exc.IntegrityError):
        _insert_startup(db_at_0007, uuid.uuid4())
    with pytest.raises(sa.exc.IntegrityError):
        _insert_submission(db_at_0007, uuid.uuid4())


def test_downgrade_removes_startup_tables_and_preserves_all_auth_tables(
    db_at_0007, alembic_config, run_alembic
):
    founder_id = _insert_founder(db_at_0007)
    startup = _insert_startup(db_at_0007, founder_id)
    _insert_submission(db_at_0007, startup["id"])
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
            {"user_id": str(founder_id), "token_hash": uuid.uuid4().bytes + uuid.uuid4().bytes},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO auth_sessions (user_id, family_id, token_hash, expires_at) "
                "VALUES (:user_id, :family_id, :token_hash, now() + interval '30 days')"
            ),
            {
                "user_id": str(founder_id),
                "family_id": str(uuid.uuid4()),
                "token_hash": uuid.uuid4().bytes + uuid.uuid4().bytes,
            },
        )
        await conn.execute(
            sa.text(
                "INSERT INTO audit_log (actor_type, action, entity_type) "
                "VALUES ('system', 'migration.startups_test', 'user')"
            )
        )

    _db(db_at_0007, seed)
    try:
        run_alembic(command.downgrade, alembic_config, "0006_auth_sessions")

        for table in ("startups", "submissions"):
            (reg,) = _scalars(db_at_0007, f"SELECT to_regclass('public.{table}')")
            assert reg is None, f"downgrade must drop the {table} table"
        assert _scalars(
            db_at_0007,
            "SELECT count(*) FROM pg_type WHERE typname = 'startup_status'",
        ) == [0], "downgrade must drop the startup_status enum"

        assert _scalars(
            db_at_0007, "SELECT count(*) FROM users WHERE id = :id", id=str(founder_id)
        ) == [1], "downgrade must preserve users"
        assert _scalars(
            db_at_0007,
            "SELECT count(*) FROM auth_sessions WHERE user_id = :id",
            id=str(founder_id),
        ) == [1], "downgrade must preserve auth sessions"
        assert _scalars(
            db_at_0007, "SELECT count(*) FROM email_tokens WHERE user_id = :id", id=str(founder_id)
        ) == [1], "downgrade must preserve email tokens"
        assert _scalars(
            db_at_0007, "SELECT email FROM invites WHERE email = :email", email=invite_email
        ) == [invite_email], "downgrade must preserve invites"
        assert (
            _scalars(
                db_at_0007,
                "SELECT count(*) FROM audit_log WHERE action = 'migration.startups_test'",
            )[0]
            >= 1
        ), "downgrade must preserve the audit trail"
        (sentinel,) = _scalars(db_at_0007, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0007, "SELECT version_num FROM alembic_version") == [
            "0006_auth_sessions"
        ]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")

        async def cleanup(conn):
            await conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}"))
            await conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": str(founder_id)})
            await conn.execute(
                sa.text("DELETE FROM invites WHERE email = :email"), {"email": invite_email}
            )

        _db(db_at_0007, cleanup)


def test_startups_revision_precedes_current_head(alembic_head):
    assert alembic_head == "0008_pitch_decks"
