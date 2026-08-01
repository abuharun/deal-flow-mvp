"""Migration tests for revision 0009_payment_consent against real Postgres.

payments stores exactly one honest demo/pilot payment row per startup
(UNIQUE startup_id FK, ON DELETE CASCADE) with defence-in-depth CHECKs: mode
is permanently 'demo', status is 'paid' or 'failed', label is the fixed
honest string 'demo_payment', and paid_at must be set iff status is 'paid'.

consents stores explicit, versioned, per-startup AI/privacy consent grants
(startup_id + founder_id FKs, ON DELETE CASCADE) with a UNIQUE
(startup_id, kind, text_version) so the same grant can never be duplicated,
while a different text_version is a brand-new row — consent history across
versions is preserved, never overwritten.

Downgrade must remove exactly these two tables and leave every earlier table
(users, startups, submissions, pitch_decks, ...) untouched.
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

SENTINEL_TABLE = "b8_payment_consent_sentinel"


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


def _insert_founder_with_startup(database_url: str) -> tuple[uuid.UUID, uuid.UUID]:
    email = f"payconsent-{uuid.uuid4().hex}@example.com"

    async def fn(conn):
        founder_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role) "
                    "VALUES (:email, 'x', 'Payment Owner', 'founder') RETURNING id"
                ),
                {"email": email},
            )
        ).scalar_one()
        startup_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO startups (founder_id, name) "
                    "VALUES (:founder_id, 'Payment Startup') RETURNING id"
                ),
                {"founder_id": str(founder_id)},
            )
        ).scalar_one()
        return founder_id, startup_id

    return _db(database_url, fn)


def _insert_payment(database_url: str, startup_id: uuid.UUID, *, paid_at="now()", **overrides):
    values = {"startup_id": str(startup_id), "status": "paid"}
    values.update(overrides)
    # paid_at needs the raw SQL `now()` expression, not a bound Python value.
    if paid_at == "now()":
        paid_at_sql = "now()"
    else:
        paid_at_sql = ":paid_at"
        values["paid_at"] = paid_at
    columns_sql = ", ".join((*(k for k in values if k != "paid_at"), "paid_at"))
    placeholders_sql = ", ".join(
        (*(f":{name}" for name in values if name != "paid_at"), paid_at_sql)
    )

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO payments ({columns_sql}) VALUES ({placeholders_sql}) "
                "RETURNING id, startup_id, mode, status, label, paid_at, created_at, updated_at"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


def _insert_consent(database_url: str, startup_id: uuid.UUID, founder_id: uuid.UUID, **overrides):
    values = {
        "startup_id": str(startup_id),
        "founder_id": str(founder_id),
        "kind": "ai_privacy",
        "text_version": "ai-privacy.v1",
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO consents ({columns}) VALUES ({placeholders}) "
                "RETURNING id, startup_id, founder_id, kind, text_version, granted_at"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


@pytest.fixture()
def db_at_0009(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0008_pitch_decks")
    run_alembic(command.upgrade, alembic_config, "0009_payment_consent")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


def test_payments_columns_types_nullability_and_defaults(db_at_0009):
    cols = _column_info(db_at_0009, "payments")
    expected = {
        "id": ("uuid", "NO"),
        "startup_id": ("uuid", "NO"),
        "mode": ("text", "NO"),
        "status": ("text", "NO"),
        "label": ("text", "NO"),
        "paid_at": ("timestamptz", "YES"),
        "created_at": ("timestamptz", "NO"),
        "updated_at": ("timestamptz", "NO"),
    }
    assert set(cols) == set(expected)
    for name, (udt, nullable) in expected.items():
        assert cols[name]["udt_name"] == udt, name
        assert cols[name]["is_nullable"] == nullable, name
    assert "gen_random_uuid()" in cols["id"]["column_default"]
    assert "demo" in cols["mode"]["column_default"]
    assert "demo_payment" in cols["label"]["column_default"]
    assert "now()" in cols["created_at"]["column_default"]


def test_consents_columns_types_nullability_and_defaults(db_at_0009):
    cols = _column_info(db_at_0009, "consents")
    expected = {
        "id": ("uuid", "NO"),
        "startup_id": ("uuid", "NO"),
        "founder_id": ("uuid", "NO"),
        "kind": ("text", "NO"),
        "text_version": ("text", "NO"),
        "granted_at": ("timestamptz", "NO"),
    }
    assert set(cols) == set(expected)
    for name, (udt, nullable) in expected.items():
        assert cols[name]["udt_name"] == udt, name
        assert cols[name]["is_nullable"] == nullable, name
    assert "gen_random_uuid()" in cols["id"]["column_default"]
    assert "now()" in cols["granted_at"]["column_default"]


def test_valid_payment_row_roundtrips(db_at_0009):
    _, startup_id = _insert_founder_with_startup(db_at_0009)
    payment = _insert_payment(db_at_0009, startup_id, status="paid", paid_at="now()")
    assert isinstance(payment["id"], uuid.UUID)
    assert payment["mode"] == "demo"
    assert payment["status"] == "paid"
    assert payment["label"] == "demo_payment"
    assert payment["paid_at"] is not None
    assert payment["created_at"].tzinfo is not None


def test_startup_id_is_unique_one_payment_per_startup(db_at_0009):
    _, startup_id = _insert_founder_with_startup(db_at_0009)
    _insert_payment(db_at_0009, startup_id, status="paid", paid_at="now()")
    with pytest.raises(sa.exc.IntegrityError):
        _insert_payment(db_at_0009, startup_id, status="paid", paid_at="now()")


def test_payment_is_deleted_with_its_startup(db_at_0009):
    founder_id, startup_id = _insert_founder_with_startup(db_at_0009)
    payment = _insert_payment(db_at_0009, startup_id, status="paid", paid_at="now()")
    _db(
        db_at_0009,
        lambda conn: conn.execute(
            sa.text("DELETE FROM startups WHERE id = :id"), {"id": str(startup_id)}
        ),
    )
    assert _scalars(
        db_at_0009, "SELECT count(*) FROM payments WHERE id = :id", id=payment["id"]
    ) == [0]


def test_orphan_payment_is_rejected(db_at_0009):
    with pytest.raises(sa.exc.IntegrityError):
        _insert_payment(db_at_0009, uuid.uuid4(), status="paid", paid_at="now()")


def test_mode_must_be_exactly_demo(db_at_0009):
    _, startup_id = _insert_founder_with_startup(db_at_0009)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_payment(db_at_0009, startup_id, mode="real", status="paid", paid_at="now()")


def test_label_must_be_exactly_demo_payment(db_at_0009):
    _, startup_id = _insert_founder_with_startup(db_at_0009)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_payment(db_at_0009, startup_id, label="charged", status="paid", paid_at="now()")


def test_status_must_be_paid_or_failed(db_at_0009):
    _, startup_id = _insert_founder_with_startup(db_at_0009)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_payment(db_at_0009, startup_id, status="pending", paid_at=None)


def test_paid_status_requires_paid_at(db_at_0009):
    _, startup_id = _insert_founder_with_startup(db_at_0009)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_payment(db_at_0009, startup_id, status="paid", paid_at=None)


def test_failed_status_forbids_paid_at(db_at_0009):
    _, startup_id = _insert_founder_with_startup(db_at_0009)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_payment(db_at_0009, startup_id, status="failed", paid_at="now()")


def test_valid_failed_payment_roundtrips(db_at_0009):
    _, startup_id = _insert_founder_with_startup(db_at_0009)
    payment = _insert_payment(db_at_0009, startup_id, status="failed", paid_at=None)
    assert payment["status"] == "failed"
    assert payment["paid_at"] is None


def test_valid_consent_row_roundtrips(db_at_0009):
    founder_id, startup_id = _insert_founder_with_startup(db_at_0009)
    consent = _insert_consent(db_at_0009, startup_id, founder_id)
    assert isinstance(consent["id"], uuid.UUID)
    assert consent["kind"] == "ai_privacy"
    assert consent["text_version"] == "ai-privacy.v1"
    assert consent["granted_at"].tzinfo is not None


def test_same_startup_kind_version_cannot_be_granted_twice(db_at_0009):
    founder_id, startup_id = _insert_founder_with_startup(db_at_0009)
    _insert_consent(db_at_0009, startup_id, founder_id)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_consent(db_at_0009, startup_id, founder_id)


def test_a_new_text_version_is_a_distinct_row_preserving_history(db_at_0009):
    founder_id, startup_id = _insert_founder_with_startup(db_at_0009)
    first = _insert_consent(db_at_0009, startup_id, founder_id, text_version="ai-privacy.v1")
    second = _insert_consent(db_at_0009, startup_id, founder_id, text_version="ai-privacy.v2")
    assert first["id"] != second["id"]
    rows = _scalars(
        db_at_0009,
        "SELECT text_version FROM consents WHERE startup_id = :id ORDER BY text_version",
        id=startup_id,
    )
    assert rows == ["ai-privacy.v1", "ai-privacy.v2"]


def test_consent_kind_must_be_exactly_ai_privacy(db_at_0009):
    founder_id, startup_id = _insert_founder_with_startup(db_at_0009)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_consent(db_at_0009, startup_id, founder_id, kind="marketing")


@pytest.mark.parametrize("text_version", ["", "x" * 33])
def test_consent_text_version_must_be_1_to_32_chars(db_at_0009, text_version):
    founder_id, startup_id = _insert_founder_with_startup(db_at_0009)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_consent(db_at_0009, startup_id, founder_id, text_version=text_version)


def test_consent_is_deleted_with_its_startup(db_at_0009):
    founder_id, startup_id = _insert_founder_with_startup(db_at_0009)
    consent = _insert_consent(db_at_0009, startup_id, founder_id)
    _db(
        db_at_0009,
        lambda conn: conn.execute(
            sa.text("DELETE FROM startups WHERE id = :id"), {"id": str(startup_id)}
        ),
    )
    assert _scalars(
        db_at_0009, "SELECT count(*) FROM consents WHERE id = :id", id=consent["id"]
    ) == [0]


def test_orphan_consent_is_rejected(db_at_0009):
    with pytest.raises(sa.exc.IntegrityError):
        _insert_consent(db_at_0009, uuid.uuid4(), uuid.uuid4())


def test_downgrade_removes_payments_and_consents_and_preserves_earlier_tables(
    db_at_0009, alembic_config, run_alembic
):
    founder_id, startup_id = _insert_founder_with_startup(db_at_0009)
    _insert_payment(db_at_0009, startup_id, status="paid", paid_at="now()")
    _insert_consent(db_at_0009, startup_id, founder_id)

    async def seed(conn):
        await conn.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {SENTINEL_TABLE} (id int)"))
        await conn.execute(
            sa.text("INSERT INTO submissions (startup_id) VALUES (:startup_id)"),
            {"startup_id": str(startup_id)},
        )

    _db(db_at_0009, seed)
    try:
        run_alembic(command.downgrade, alembic_config, "0008_pitch_decks")

        for table in ("payments", "consents"):
            (reg,) = _scalars(db_at_0009, f"SELECT to_regclass('public.{table}')")
            assert reg is None, f"downgrade must drop the {table} table"

        assert _scalars(
            db_at_0009, "SELECT count(*) FROM users WHERE id = :id", id=str(founder_id)
        ) == [1], "downgrade must preserve users"
        assert _scalars(
            db_at_0009, "SELECT count(*) FROM startups WHERE id = :id", id=str(startup_id)
        ) == [1], "downgrade must preserve startups"
        assert _scalars(
            db_at_0009,
            "SELECT count(*) FROM submissions WHERE startup_id = :id",
            id=str(startup_id),
        ) == [1], "downgrade must preserve submissions"
        (sentinel,) = _scalars(db_at_0009, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0009, "SELECT version_num FROM alembic_version") == [
            "0008_pitch_decks"
        ]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")

        async def cleanup(conn):
            await conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}"))
            await conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": str(founder_id)})

        _db(db_at_0009, cleanup)


def test_head_is_0009(alembic_head):
    assert alembic_head == "0009_payment_consent"
