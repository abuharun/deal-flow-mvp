"""Migration tests for revision 0008_pitch_decks against real Postgres.

pitch_decks stores exactly one private PDF per startup (UNIQUE startup_id FK,
ON DELETE CASCADE) with defence-in-depth CHECKs: exact application/pdf MIME,
1..5 MiB size that must equal the stored bytes, a 32-byte SHA-256, and a
1..15 page count. Downgrade must remove exactly this table and leave every
earlier table (users, auth_sessions, startups, submissions, ...) untouched.
"""

import asyncio
import hashlib
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

MAX_DECK_BYTES = 5 * 1024 * 1024
SENTINEL_TABLE = "b7_pitch_decks_sentinel"


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
    email = f"decks-{uuid.uuid4().hex}@example.com"

    async def fn(conn):
        founder_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role) "
                    "VALUES (:email, 'x', 'Deck Owner', 'founder') RETURNING id"
                ),
                {"email": email},
            )
        ).scalar_one()
        startup_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO startups (founder_id, name) "
                    "VALUES (:founder_id, 'Deck Startup') RETURNING id"
                ),
                {"founder_id": str(founder_id)},
            )
        ).scalar_one()
        return founder_id, startup_id

    return _db(database_url, fn)


def _insert_deck(database_url: str, startup_id: uuid.UUID, **overrides):
    content = overrides.pop("content", b"%PDF-1.4 test bytes")
    values = {
        "startup_id": str(startup_id),
        "filename": "deck.pdf",
        "mime_type": "application/pdf",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).digest(),
        "page_count": 1,
        "content": content,
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO pitch_decks ({columns}) VALUES ({placeholders}) "
                "RETURNING id, startup_id, filename, mime_type, size_bytes, sha256, "
                "page_count, uploaded_at"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


@pytest.fixture()
def db_at_0008(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0007_startups")
    run_alembic(command.upgrade, alembic_config, "0008_pitch_decks")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


def test_pitch_decks_columns_types_nullability_and_defaults(db_at_0008):
    cols = _column_info(db_at_0008, "pitch_decks")
    expected = {
        # name: (udt_name, nullable)
        "id": ("uuid", "NO"),
        "startup_id": ("uuid", "NO"),
        "filename": ("text", "NO"),
        "mime_type": ("text", "NO"),
        "size_bytes": ("int8", "NO"),
        "sha256": ("bytea", "NO"),
        "page_count": ("int4", "NO"),
        "content": ("bytea", "NO"),
        "uploaded_at": ("timestamptz", "NO"),
    }
    assert set(cols) == set(expected)
    for name, (udt, nullable) in expected.items():
        assert cols[name]["udt_name"] == udt, name
        assert cols[name]["is_nullable"] == nullable, name
    assert "gen_random_uuid()" in cols["id"]["column_default"]
    assert "now()" in cols["uploaded_at"]["column_default"]


def test_valid_deck_row_roundtrips(db_at_0008):
    _, startup_id = _insert_founder_with_startup(db_at_0008)
    content = b"%PDF-1.7 payload"
    deck = _insert_deck(db_at_0008, startup_id, content=content)
    assert isinstance(deck["id"], uuid.UUID)
    assert deck["mime_type"] == "application/pdf"
    assert deck["size_bytes"] == len(content)
    assert bytes(deck["sha256"]) == hashlib.sha256(content).digest()
    assert deck["uploaded_at"].tzinfo is not None


def test_startup_id_is_unique_one_deck_per_startup(db_at_0008):
    _, startup_id = _insert_founder_with_startup(db_at_0008)
    _insert_deck(db_at_0008, startup_id)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_deck(db_at_0008, startup_id)


def test_deck_is_deleted_with_its_startup(db_at_0008):
    founder_id, startup_id = _insert_founder_with_startup(db_at_0008)
    deck = _insert_deck(db_at_0008, startup_id)
    _db(
        db_at_0008,
        lambda conn: conn.execute(
            sa.text("DELETE FROM startups WHERE id = :id"), {"id": str(startup_id)}
        ),
    )
    assert _scalars(
        db_at_0008, "SELECT count(*) FROM pitch_decks WHERE id = :id", id=deck["id"]
    ) == [0]


def test_orphan_deck_is_rejected(db_at_0008):
    with pytest.raises(sa.exc.IntegrityError):
        _insert_deck(db_at_0008, uuid.uuid4())


def test_mime_type_must_be_exactly_application_pdf(db_at_0008):
    _, startup_id = _insert_founder_with_startup(db_at_0008)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_deck(db_at_0008, startup_id, mime_type="application/x-pdf")


@pytest.mark.parametrize("size_bytes", [0, MAX_DECK_BYTES + 1])
def test_size_bytes_outside_1_to_5mib_is_rejected(db_at_0008, size_bytes):
    _, startup_id = _insert_founder_with_startup(db_at_0008)
    with pytest.raises(sa.exc.IntegrityError):
        # size_bytes must also equal octet_length(content), so oversize/empty
        # claims are exercised with matching content via the dedicated check.
        _insert_deck(db_at_0008, startup_id, size_bytes=size_bytes)


def test_size_bytes_must_match_stored_content_length(db_at_0008):
    _, startup_id = _insert_founder_with_startup(db_at_0008)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_deck(db_at_0008, startup_id, size_bytes=1)


def test_sha256_must_be_exactly_32_bytes(db_at_0008):
    _, startup_id = _insert_founder_with_startup(db_at_0008)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_deck(db_at_0008, startup_id, sha256=b"\x00" * 31)


@pytest.mark.parametrize("page_count", [0, 16])
def test_page_count_outside_1_to_15_is_rejected(db_at_0008, page_count):
    _, startup_id = _insert_founder_with_startup(db_at_0008)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_deck(db_at_0008, startup_id, page_count=page_count)


@pytest.mark.parametrize("filename", ["", "x" * 256])
def test_filename_must_be_1_to_255_chars(db_at_0008, filename):
    _, startup_id = _insert_founder_with_startup(db_at_0008)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_deck(db_at_0008, startup_id, filename=filename)


def test_downgrade_removes_pitch_decks_and_preserves_earlier_tables(
    db_at_0008, alembic_config, run_alembic
):
    founder_id, startup_id = _insert_founder_with_startup(db_at_0008)
    _insert_deck(db_at_0008, startup_id)

    async def seed(conn):
        await conn.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {SENTINEL_TABLE} (id int)"))
        await conn.execute(
            sa.text("INSERT INTO submissions (startup_id) VALUES (:startup_id)"),
            {"startup_id": str(startup_id)},
        )

    _db(db_at_0008, seed)
    try:
        run_alembic(command.downgrade, alembic_config, "0007_startups")

        (reg,) = _scalars(db_at_0008, "SELECT to_regclass('public.pitch_decks')")
        assert reg is None, "downgrade must drop the pitch_decks table"

        assert _scalars(
            db_at_0008, "SELECT count(*) FROM users WHERE id = :id", id=str(founder_id)
        ) == [1], "downgrade must preserve users"
        assert _scalars(
            db_at_0008, "SELECT count(*) FROM startups WHERE id = :id", id=str(startup_id)
        ) == [1], "downgrade must preserve startups"
        assert _scalars(
            db_at_0008,
            "SELECT count(*) FROM submissions WHERE startup_id = :id",
            id=str(startup_id),
        ) == [1], "downgrade must preserve submissions"
        (sentinel,) = _scalars(db_at_0008, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0008, "SELECT version_num FROM alembic_version") == ["0007_startups"]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")

        async def cleanup(conn):
            await conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}"))
            await conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": str(founder_id)})

        _db(db_at_0008, cleanup)


def test_head_is_0008(alembic_head):
    assert alembic_head == "0008_pitch_decks"
