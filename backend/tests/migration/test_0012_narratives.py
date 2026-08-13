"""Migration tests for revision 0012_narratives against real Postgres.

narrative_versions is an append-only history: one row per saved version of a
startup's single free-text pitch narrative, numbered monotonically per
startup (UNIQUE (startup_id, version)) and carrying the provenance the
version was written against (report_id + the startup's input_revision at
save time). Rows reject UPDATE and DELETE via a DB trigger -- REVOKE alone
cannot bind the table owner, which is exactly who the app connects as.

startup_narratives is the mutable one-per-startup CURRENT pointer: it holds
no text of its own, only (startup_id UNIQUE, current_version), with a
composite FK into narrative_versions (startup_id, version) so the pointer
can never name a version that does not exist -- or one belonging to another
startup. That row is deliberately UPDATE-able: moving the pointer forward is
how a save takes effect, and it is the only mutable half of this feature.

Downgrade must remove exactly these two tables (and the trigger function)
and leave every earlier table untouched.
"""

import asyncio
import json
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

SENTINEL_TABLE = "b12_narratives_sentinel"

MAX_CONTENT_LENGTH = 20_000


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
    email = f"narrative-{uuid.uuid4().hex}@example.com"

    async def fn(conn):
        founder_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role) "
                    "VALUES (:email, 'x', 'Narrative Owner', 'founder') RETURNING id"
                ),
                {"email": email},
            )
        ).scalar_one()
        startup_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO startups (founder_id, name) "
                    "VALUES (:founder_id, 'Narrative Startup') RETURNING id"
                ),
                {"founder_id": str(founder_id)},
            )
        ).scalar_one()
        return founder_id, startup_id

    return _db(database_url, fn)


def _insert_report(database_url: str, startup_id: uuid.UUID) -> uuid.UUID:
    async def fn(conn):
        job_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO analysis_jobs (startup_id, input_revision) "
                    "VALUES (:startup_id, 1) RETURNING id"
                ),
                {"startup_id": str(startup_id)},
            )
        ).scalar_one()
        return (
            await conn.execute(
                sa.text(
                    "INSERT INTO analysis_reports "
                    "(startup_id, job_id, input_revision, report, model, prompt_version, "
                    "generated_at) VALUES (:startup_id, :job_id, 1, :report, 'gpt-test', 'v1', "
                    "now()) RETURNING id"
                ),
                {
                    "startup_id": str(startup_id),
                    "job_id": str(job_id),
                    "report": json.dumps({"pitch_narrative_draft": "seed"}),
                },
            )
        ).scalar_one()

    return _db(database_url, fn)


def _seeded(database_url: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A founder, their startup, and that startup's immutable report."""
    founder_id, startup_id = _insert_founder_with_startup(database_url)
    return founder_id, startup_id, _insert_report(database_url, startup_id)


def _insert_version(
    database_url: str,
    startup_id: uuid.UUID,
    report_id: uuid.UUID,
    founder_id: uuid.UUID,
    **overrides,
):
    values = {
        "startup_id": str(startup_id),
        "version": 1,
        "content": "Our narrative, in the founder's chosen language.",
        "source": "report_seed",
        "report_id": str(report_id),
        "input_revision": 1,
        "created_by": str(founder_id),
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO narrative_versions ({columns}) VALUES ({placeholders}) "
                "RETURNING id, startup_id, version, content, source, report_id, input_revision, "
                "created_by, created_at"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


def _insert_current(database_url: str, startup_id: uuid.UUID, **overrides):
    values = {"startup_id": str(startup_id), "current_version": 1}
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO startup_narratives ({columns}) VALUES ({placeholders}) "
                "RETURNING id, startup_id, current_version, created_at, updated_at"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


@pytest.fixture()
def db_at_0012(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0011_analysis_reports")
    run_alembic(command.upgrade, alembic_config, "0012_narratives")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


class TestColumnsAndDefaults:
    def test_narrative_versions_columns_types_nullability_and_defaults(self, db_at_0012):
        cols = _column_info(db_at_0012, "narrative_versions")
        expected = {
            "id": ("uuid", "NO"),
            "startup_id": ("uuid", "NO"),
            "version": ("int4", "NO"),
            "content": ("text", "NO"),
            "source": ("text", "NO"),
            "report_id": ("uuid", "NO"),
            "input_revision": ("int4", "NO"),
            "created_by": ("uuid", "NO"),
            "created_at": ("timestamptz", "NO"),
        }
        assert set(cols) == set(expected)
        for name, (udt, nullable) in expected.items():
            assert cols[name]["udt_name"] == udt, name
            assert cols[name]["is_nullable"] == nullable, name
        assert "gen_random_uuid()" in cols["id"]["column_default"]
        assert "now()" in cols["created_at"]["column_default"]

    def test_startup_narratives_columns_types_nullability_and_defaults(self, db_at_0012):
        cols = _column_info(db_at_0012, "startup_narratives")
        expected = {
            "id": ("uuid", "NO"),
            "startup_id": ("uuid", "NO"),
            "current_version": ("int4", "NO"),
            "created_at": ("timestamptz", "NO"),
            "updated_at": ("timestamptz", "NO"),
        }
        assert set(cols) == set(expected)
        for name, (udt, nullable) in expected.items():
            assert cols[name]["udt_name"] == udt, name
            assert cols[name]["is_nullable"] == nullable, name
        assert "gen_random_uuid()" in cols["id"]["column_default"]

    def test_the_current_pointer_carries_no_narrative_text_of_its_own(self, db_at_0012):
        # The pointer must never duplicate content: the current narrative IS
        # the immutable version row it names, so the two can never diverge.
        cols = _column_info(db_at_0012, "startup_narratives")
        assert "content" not in cols


class TestValidRoundtrip:
    def test_valid_version_and_current_pointer_roundtrip(self, db_at_0012):
        founder_id, startup_id, report_id = _seeded(db_at_0012)

        version = _insert_version(db_at_0012, startup_id, report_id, founder_id)
        assert version["version"] == 1
        assert version["source"] == "report_seed"
        assert version["input_revision"] == 1

        current = _insert_current(db_at_0012, startup_id)
        assert current["current_version"] == 1
        assert current["created_at"] is not None

    def test_content_keeps_newlines_tabs_and_non_ascii_text(self, db_at_0012):
        # The founder chooses the narrative's language; UZ/RU/EN text and
        # ordinary markdown whitespace must all survive a roundtrip intact.
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        content = "## Биз ким\n\n- Тошкент\tмаркет\n- Рынок растёт"

        version = _insert_version(db_at_0012, startup_id, report_id, founder_id, content=content)

        assert version["content"] == content

    def test_content_at_the_length_limit_is_accepted(self, db_at_0012):
        founder_id, startup_id, report_id = _seeded(db_at_0012)

        version = _insert_version(
            db_at_0012, startup_id, report_id, founder_id, content="x" * MAX_CONTENT_LENGTH
        )

        assert len(version["content"]) == MAX_CONTENT_LENGTH


class TestForeignKeysAndUniqueness:
    def test_orphan_startup_is_rejected(self, db_at_0012):
        founder_id, _, report_id = _seeded(db_at_0012)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_version(db_at_0012, uuid.uuid4(), report_id, founder_id)

    def test_orphan_report_is_rejected(self, db_at_0012):
        founder_id, startup_id, _ = _seeded(db_at_0012)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_version(db_at_0012, startup_id, uuid.uuid4(), founder_id)

    def test_orphan_author_is_rejected(self, db_at_0012):
        _, startup_id, report_id = _seeded(db_at_0012)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_version(db_at_0012, startup_id, report_id, uuid.uuid4())

    def test_version_is_unique_within_a_startup(self, db_at_0012):
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        _insert_version(db_at_0012, startup_id, report_id, founder_id, version=1)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_version(db_at_0012, startup_id, report_id, founder_id, version=1)

    def test_same_version_number_is_fine_across_different_startups(self, db_at_0012):
        founder_a, startup_a, report_a = _seeded(db_at_0012)
        founder_b, startup_b, report_b = _seeded(db_at_0012)

        _insert_version(db_at_0012, startup_a, report_a, founder_a, version=1)
        _insert_version(db_at_0012, startup_b, report_b, founder_b, version=1)

    def test_only_one_current_narrative_per_startup(self, db_at_0012):
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        _insert_version(db_at_0012, startup_id, report_id, founder_id, version=1)
        _insert_version(db_at_0012, startup_id, report_id, founder_id, version=2)
        _insert_current(db_at_0012, startup_id, current_version=1)

        with pytest.raises(sa.exc.IntegrityError):
            _insert_current(db_at_0012, startup_id, current_version=2)

    def test_current_pointer_must_name_an_existing_version(self, db_at_0012):
        _, startup_id, _ = _seeded(db_at_0012)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_current(db_at_0012, startup_id, current_version=1)

    def test_current_pointer_cannot_name_another_startups_version(self, db_at_0012):
        founder_a, startup_a, report_a = _seeded(db_at_0012)
        _, startup_b, _ = _seeded(db_at_0012)
        _insert_version(db_at_0012, startup_a, report_a, founder_a, version=1)

        with pytest.raises(sa.exc.IntegrityError):
            _insert_current(db_at_0012, startup_b, current_version=1)

    def test_narrative_rows_are_deleted_when_the_startup_is_hard_deleted(self, db_at_0012):
        # A direct application/admin DELETE is always rejected, but a cascade
        # from hard-deleting the owning startup must still work end to end --
        # otherwise account deletion would be impossible once a founder has
        # written a narrative.
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        version = _insert_version(db_at_0012, startup_id, report_id, founder_id)
        current = _insert_current(db_at_0012, startup_id)

        _db(
            db_at_0012,
            lambda conn: conn.execute(
                sa.text("DELETE FROM startups WHERE id = :id"), {"id": str(startup_id)}
            ),
        )

        assert _scalars(
            db_at_0012, "SELECT count(*) FROM narrative_versions WHERE id = :id", id=version["id"]
        ) == [0]
        assert _scalars(
            db_at_0012, "SELECT count(*) FROM startup_narratives WHERE id = :id", id=current["id"]
        ) == [0]


class TestChecks:
    def test_version_must_be_at_least_1(self, db_at_0012):
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_version(db_at_0012, startup_id, report_id, founder_id, version=0)

    def test_input_revision_must_be_at_least_1(self, db_at_0012):
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_version(db_at_0012, startup_id, report_id, founder_id, input_revision=0)

    def test_current_version_must_be_at_least_1(self, db_at_0012):
        _, startup_id, _ = _seeded(db_at_0012)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_current(db_at_0012, startup_id, current_version=0)

    @pytest.mark.parametrize("content", ["", "   \n\t  ", "x" * (MAX_CONTENT_LENGTH + 1)])
    def test_empty_blank_and_overlong_content_is_rejected(self, db_at_0012, content):
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_version(db_at_0012, startup_id, report_id, founder_id, content=content)

    @pytest.mark.parametrize("control", ["\r", "\x01", "\x0b", "\x0c", "\x1f", "\x7f"])
    def test_control_characters_other_than_newline_and_tab_are_rejected(self, db_at_0012, control):
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_version(
                db_at_0012, startup_id, report_id, founder_id, content=f"before{control}after"
            )

    def test_content_with_a_null_byte_is_rejected(self, db_at_0012):
        # asyncpg refuses a NUL byte while encoding the bind parameter itself
        # (PostgreSQL's text wire format cannot carry \x00 at all), so this
        # surfaces as a DBAPIError rather than reaching the CHECK -- still
        # never stored, and the request schema strips control characters long
        # before any value reaches the database.
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        with pytest.raises(sa.exc.DBAPIError):
            _insert_version(
                db_at_0012, startup_id, report_id, founder_id, content="before\x00after"
            )

    @pytest.mark.parametrize("source", ["", "REPORT_SEED", "manual", "founder-edit"])
    def test_source_must_be_one_of_the_canonical_values(self, db_at_0012, source):
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_version(db_at_0012, startup_id, report_id, founder_id, source=source)

    def test_founder_edit_is_a_canonical_source(self, db_at_0012):
        founder_id, startup_id, report_id = _seeded(db_at_0012)

        version = _insert_version(
            db_at_0012, startup_id, report_id, founder_id, source="founder_edit"
        )

        assert version["source"] == "founder_edit"


class TestImmutability:
    def test_update_on_narrative_versions_is_rejected(self, db_at_0012):
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        version = _insert_version(db_at_0012, startup_id, report_id, founder_id)

        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            _db(
                db_at_0012,
                lambda conn: conn.execute(
                    sa.text("UPDATE narrative_versions SET content = 'tampered' WHERE id = :id"),
                    {"id": version["id"]},
                ),
            )

        assert _scalars(
            db_at_0012, "SELECT content FROM narrative_versions WHERE id = :id", id=version["id"]
        ) == [version["content"]]

    def test_delete_on_narrative_versions_is_rejected(self, db_at_0012):
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        version = _insert_version(db_at_0012, startup_id, report_id, founder_id)

        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            _db(
                db_at_0012,
                lambda conn: conn.execute(
                    sa.text("DELETE FROM narrative_versions WHERE id = :id"), {"id": version["id"]}
                ),
            )

        assert _scalars(
            db_at_0012, "SELECT count(*) FROM narrative_versions WHERE id = :id", id=version["id"]
        ) == [1]

    def test_history_survives_an_attempt_to_rewrite_an_older_version(self, db_at_0012):
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        _insert_version(db_at_0012, startup_id, report_id, founder_id, version=1, content="first")
        _insert_version(
            db_at_0012,
            startup_id,
            report_id,
            founder_id,
            version=2,
            content="second",
            source="founder_edit",
        )

        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            _db(
                db_at_0012,
                lambda conn: conn.execute(
                    sa.text(
                        "UPDATE narrative_versions SET content = 'rewritten' "
                        "WHERE startup_id = :id AND version = 1"
                    ),
                    {"id": str(startup_id)},
                ),
            )

        assert _scalars(
            db_at_0012,
            "SELECT content FROM narrative_versions WHERE startup_id = :id ORDER BY version",
            id=str(startup_id),
        ) == ["first", "second"]

    def test_the_current_pointer_stays_updatable(self, db_at_0012):
        # The only mutable half of the feature: a save moves this pointer
        # forward, it never edits a version row.
        founder_id, startup_id, report_id = _seeded(db_at_0012)
        _insert_version(db_at_0012, startup_id, report_id, founder_id, version=1)
        _insert_version(
            db_at_0012, startup_id, report_id, founder_id, version=2, source="founder_edit"
        )
        _insert_current(db_at_0012, startup_id, current_version=1)

        _db(
            db_at_0012,
            lambda conn: conn.execute(
                sa.text("UPDATE startup_narratives SET current_version = 2 WHERE startup_id = :id"),
                {"id": str(startup_id)},
            ),
        )

        assert _scalars(
            db_at_0012,
            "SELECT current_version FROM startup_narratives WHERE startup_id = :id",
            id=str(startup_id),
        ) == [2]


def test_downgrade_removes_narrative_tables_and_preserves_earlier_tables(
    db_at_0012, alembic_config, run_alembic
):
    founder_id, startup_id, report_id = _seeded(db_at_0012)
    _insert_version(db_at_0012, startup_id, report_id, founder_id)
    _insert_current(db_at_0012, startup_id)

    async def seed(conn):
        await conn.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {SENTINEL_TABLE} (id int)"))

    _db(db_at_0012, seed)
    try:
        run_alembic(command.downgrade, alembic_config, "0011_analysis_reports")

        (versions_reg,) = _scalars(db_at_0012, "SELECT to_regclass('public.narrative_versions')")
        assert versions_reg is None, "downgrade must drop the narrative_versions table"
        (current_reg,) = _scalars(db_at_0012, "SELECT to_regclass('public.startup_narratives')")
        assert current_reg is None, "downgrade must drop the startup_narratives table"
        assert _scalars(
            db_at_0012,
            "SELECT count(*) FROM pg_proc WHERE proname = 'narrative_version_block_mutation'",
        ) == [0], "downgrade must drop the immutability trigger function"

        assert _scalars(
            db_at_0012, "SELECT count(*) FROM startups WHERE id = :id", id=str(startup_id)
        ) == [1], "downgrade must preserve startups"
        assert _scalars(
            db_at_0012, "SELECT count(*) FROM analysis_reports WHERE id = :id", id=str(report_id)
        ) == [1], "downgrade must preserve analysis_reports"
        (sentinel,) = _scalars(db_at_0012, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0012, "SELECT version_num FROM alembic_version") == [
            "0011_analysis_reports"
        ]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")

        async def cleanup(conn):
            await conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}"))

        _db(db_at_0012, cleanup)


def test_head_is_0012(alembic_head):
    assert alembic_head == "0012_narratives"
