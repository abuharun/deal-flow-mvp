"""Migration tests for revision 0011_analysis_reports against real Postgres.

analysis_reports stores exactly one immutable report per startup and per
analysis job (both UNIQUE, FK ON DELETE CASCADE), pinned to the schema
version, model, prompt_version, and input_revision it was generated with.
report_sources normalizes each cited source with a per-report ordinal that
the report JSONB citation_ids reference. Both tables reject UPDATE and
DELETE via a shared DB trigger -- REVOKE alone cannot bind the table owner,
which is exactly who the app connects as.

Downgrade must remove exactly these two tables (and the trigger function)
and leave every earlier table untouched.
"""

import asyncio
import json
import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

SENTINEL_TABLE = "b11_analysis_reports_sentinel"


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
    email = f"analysisreport-{uuid.uuid4().hex}@example.com"

    async def fn(conn):
        founder_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role) "
                    "VALUES (:email, 'x', 'Report Owner', 'founder') RETURNING id"
                ),
                {"email": email},
            )
        ).scalar_one()
        startup_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO startups (founder_id, name) "
                    "VALUES (:founder_id, 'Report Startup') RETURNING id"
                ),
                {"founder_id": str(founder_id)},
            )
        ).scalar_one()
        return founder_id, startup_id

    return _db(database_url, fn)


def _insert_job(database_url: str, startup_id: uuid.UUID, **overrides) -> uuid.UUID:
    values = {"startup_id": str(startup_id), "input_revision": 1}
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        return (
            await conn.execute(
                sa.text(
                    f"INSERT INTO analysis_jobs ({columns}) VALUES ({placeholders}) RETURNING id"
                ),
                values,
            )
        ).scalar_one()

    return _db(database_url, fn)


def _insert_report(database_url: str, startup_id: uuid.UUID, job_id: uuid.UUID, **overrides):
    values = {
        "startup_id": str(startup_id),
        "job_id": str(job_id),
        "input_revision": 1,
        "report": json.dumps({"executive_summary": "ok"}),
        "model": "gpt-test",
        "prompt_version": "v1",
        "generated_at": sa.text("now()"),
    }
    values.update(overrides)
    raw_sql = {k: v.text for k, v in values.items() if isinstance(v, sa.sql.elements.TextClause)}
    bound = {k: v for k, v in values.items() if k not in raw_sql}
    columns = ", ".join(values)
    placeholders = ", ".join(raw_sql.get(name, f":{name}") for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO analysis_reports ({columns}) VALUES ({placeholders}) "
                "RETURNING id, startup_id, job_id, input_revision, schema_version, language, "
                "report, model, prompt_version, partial, evidence_count, generated_at"
            ),
            bound,
        )
        return result.mappings().one()

    return _db(database_url, fn)


def _insert_source(database_url: str, report_id: uuid.UUID, **overrides):
    values = {
        "report_id": str(report_id),
        "ordinal": 1,
        "url": "https://example.com/article",
        "title": "Example article",
        "accessed_date": date(2026, 1, 1),
        "source_quality": "reputable_media",
        "confidence": "medium",
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO report_sources ({columns}) VALUES ({placeholders}) "
                "RETURNING id, report_id, ordinal, url, title, published_date, accessed_date, "
                "source_quality, confidence, snippet"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


@pytest.fixture()
def db_at_0011(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0010_analysis_jobs")
    run_alembic(command.upgrade, alembic_config, "0011_analysis_reports")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


class TestColumnsAndDefaults:
    def test_analysis_reports_columns_types_nullability_and_defaults(self, db_at_0011):
        cols = _column_info(db_at_0011, "analysis_reports")
        expected = {
            "id": ("uuid", "NO"),
            "startup_id": ("uuid", "NO"),
            "job_id": ("uuid", "NO"),
            "input_revision": ("int4", "NO"),
            "schema_version": ("text", "NO"),
            "language": ("text", "NO"),
            "report": ("jsonb", "NO"),
            "model": ("text", "NO"),
            "prompt_version": ("text", "NO"),
            "partial": ("bool", "NO"),
            "evidence_count": ("int4", "YES"),
            "generated_at": ("timestamptz", "NO"),
            "created_at": ("timestamptz", "NO"),
        }
        assert set(cols) == set(expected)
        for name, (udt, nullable) in expected.items():
            assert cols[name]["udt_name"] == udt, name
            assert cols[name]["is_nullable"] == nullable, name
        assert "gen_random_uuid()" in cols["id"]["column_default"]
        assert "report.v1" in cols["schema_version"]["column_default"]
        assert "en" in cols["language"]["column_default"]
        assert cols["partial"]["column_default"] == "false"

    def test_report_sources_columns_types_nullability(self, db_at_0011):
        cols = _column_info(db_at_0011, "report_sources")
        expected = {
            "id": ("uuid", "NO"),
            "report_id": ("uuid", "NO"),
            "ordinal": ("int4", "NO"),
            "url": ("text", "NO"),
            "title": ("text", "NO"),
            "published_date": ("date", "YES"),
            "accessed_date": ("date", "NO"),
            "source_quality": ("text", "NO"),
            "confidence": ("text", "NO"),
            "snippet": ("text", "YES"),
        }
        assert set(cols) == set(expected)
        for name, (udt, nullable) in expected.items():
            assert cols[name]["udt_name"] == udt, name
            assert cols[name]["is_nullable"] == nullable, name


class TestValidRoundtrip:
    def test_valid_report_and_source_roundtrip(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)

        report = _insert_report(db_at_0011, startup_id, job_id)
        assert report["schema_version"] == "report.v1"
        assert report["language"] == "en"
        assert report["partial"] is False
        assert report["evidence_count"] is None

        source = _insert_source(db_at_0011, report["id"])
        assert source["ordinal"] == 1
        assert source["source_quality"] == "reputable_media"
        assert source["confidence"] == "medium"


class TestForeignKeysAndUniqueness:
    def test_orphan_report_startup_is_rejected(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_report(db_at_0011, uuid.uuid4(), job_id)

    def test_orphan_report_job_is_rejected(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_report(db_at_0011, startup_id, uuid.uuid4())

    def test_startup_id_is_unique_one_report_per_startup(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        _insert_report(db_at_0011, startup_id, job_id)
        # analysis_jobs itself only allows one job per startup, so a second
        # (validly-FK'd) job_id must come from a different startup -- report
        # rows don't cross-check that a job actually belongs to its report's
        # startup, only that both FKs individually resolve.
        _, other_startup_id = _insert_founder_with_startup(db_at_0011)
        other_job_id = _insert_job(db_at_0011, other_startup_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_report(db_at_0011, startup_id, other_job_id)

    def test_job_id_is_unique_one_report_per_job(self, db_at_0011):
        _, startup_id_1 = _insert_founder_with_startup(db_at_0011)
        _, startup_id_2 = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id_1)
        _insert_report(db_at_0011, startup_id_1, job_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_report(db_at_0011, startup_id_2, job_id)

    def test_report_and_its_sources_are_deleted_when_the_startup_is_hard_deleted(self, db_at_0011):
        # A direct application/admin DELETE is always rejected, but a
        # cascade triggered by hard-deleting the owning startup must still
        # work end to end -- otherwise account deletion would be impossible
        # once a startup has a report.
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        source = _insert_source(db_at_0011, report["id"])

        _db(
            db_at_0011,
            lambda conn: conn.execute(
                sa.text("DELETE FROM startups WHERE id = :id"), {"id": str(startup_id)}
            ),
        )

        assert _scalars(
            db_at_0011, "SELECT count(*) FROM analysis_reports WHERE id = :id", id=report["id"]
        ) == [0]
        assert _scalars(
            db_at_0011, "SELECT count(*) FROM report_sources WHERE id = :id", id=source["id"]
        ) == [0]

    def test_orphan_source_is_rejected(self, db_at_0011):
        with pytest.raises(sa.exc.IntegrityError):
            _insert_source(db_at_0011, uuid.uuid4())

    def test_ordinal_is_unique_within_a_report(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        _insert_source(db_at_0011, report["id"], ordinal=1)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_source(db_at_0011, report["id"], ordinal=1)

    def test_same_ordinal_is_fine_across_different_reports(self, db_at_0011):
        _, startup_id_1 = _insert_founder_with_startup(db_at_0011)
        _, startup_id_2 = _insert_founder_with_startup(db_at_0011)
        job_id_1 = _insert_job(db_at_0011, startup_id_1)
        job_id_2 = _insert_job(db_at_0011, startup_id_2)
        report_1 = _insert_report(db_at_0011, startup_id_1, job_id_1)
        report_2 = _insert_report(db_at_0011, startup_id_2, job_id_2)
        _insert_source(db_at_0011, report_1["id"], ordinal=1)
        _insert_source(db_at_0011, report_2["id"], ordinal=1)


class TestChecksOnAnalysisReports:
    def test_input_revision_must_be_at_least_1(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_report(db_at_0011, startup_id, job_id, input_revision=0)

    def test_schema_version_must_be_exactly_report_v1(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_report(db_at_0011, startup_id, job_id, schema_version="report.v2")

    def test_language_must_be_exactly_en(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_report(db_at_0011, startup_id, job_id, language="ru")

    @pytest.mark.parametrize("model_value", ["", "x" * 129])
    def test_model_length_must_be_1_to_128_chars(self, db_at_0011, model_value):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_report(db_at_0011, startup_id, job_id, model=model_value)

    @pytest.mark.parametrize("prompt_version", ["", "x" * 33])
    def test_prompt_version_length_must_be_1_to_32_chars(self, db_at_0011, prompt_version):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_report(db_at_0011, startup_id, job_id, prompt_version=prompt_version)

    def test_evidence_count_cannot_be_negative(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_report(db_at_0011, startup_id, job_id, evidence_count=-1)

    def test_evidence_count_of_zero_is_accepted(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id, evidence_count=0)
        assert report["evidence_count"] == 0


class TestChecksOnReportSources:
    def test_ordinal_must_be_at_least_1(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_source(db_at_0011, report["id"], ordinal=0)

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "ftp://files.example.com/room",
            "not a url",
            "https://example.com/fol der",
            "",
            "x",
        ],
    )
    def test_unsafe_or_empty_urls_are_rejected(self, db_at_0011, url):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_source(db_at_0011, report["id"], url=url)

    def test_url_with_a_null_byte_is_rejected(self, db_at_0011):
        # asyncpg refuses a NUL byte while encoding the bind parameter itself
        # (PostgreSQL's text wire format cannot carry \x00 at all), so this
        # never reaches our CHECK constraint -- it surfaces as a DBAPIError,
        # not an IntegrityError. Still proves the value is rejected and never
        # stored; the app-level schema (report.v1 SourceInput) also strips
        # control characters before any value ever reaches the DB.
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        with pytest.raises(sa.exc.DBAPIError):
            _insert_source(db_at_0011, report["id"], url="https://example.com/fol\x00der")

    def test_overlong_url_is_rejected(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_source(db_at_0011, report["id"], url="https://example.com/" + "a" * 2048)

    @pytest.mark.parametrize("title", ["", "x" * 301])
    def test_title_length_must_be_1_to_300_chars(self, db_at_0011, title):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_source(db_at_0011, report["id"], title=title)

    @pytest.mark.parametrize("value", ["", "PRIMARY", "official"])
    def test_source_quality_must_be_one_of_the_canonical_values(self, db_at_0011, value):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_source(db_at_0011, report["id"], source_quality=value)

    @pytest.mark.parametrize("value", ["", "HIGH", "certain"])
    def test_confidence_must_be_one_of_the_canonical_values(self, db_at_0011, value):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_source(db_at_0011, report["id"], confidence=value)

    def test_overlong_snippet_is_rejected(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_source(db_at_0011, report["id"], snippet="x" * 1001)

    def test_snippet_at_the_limit_is_accepted(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        source = _insert_source(db_at_0011, report["id"], snippet="x" * 1000)
        assert source["snippet"] == "x" * 1000


class TestImmutability:
    def test_update_on_analysis_reports_is_rejected(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            _db(
                db_at_0011,
                lambda conn: conn.execute(
                    sa.text("UPDATE analysis_reports SET model = 'tampered' WHERE id = :id"),
                    {"id": report["id"]},
                ),
            )
        assert _scalars(
            db_at_0011, "SELECT model FROM analysis_reports WHERE id = :id", id=report["id"]
        ) == [report["model"]]

    def test_delete_on_analysis_reports_is_rejected(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            _db(
                db_at_0011,
                lambda conn: conn.execute(
                    sa.text("DELETE FROM analysis_reports WHERE id = :id"), {"id": report["id"]}
                ),
            )
        assert _scalars(
            db_at_0011, "SELECT count(*) FROM analysis_reports WHERE id = :id", id=report["id"]
        ) == [1]

    def test_update_on_report_sources_is_rejected(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        source = _insert_source(db_at_0011, report["id"])
        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            _db(
                db_at_0011,
                lambda conn: conn.execute(
                    sa.text("UPDATE report_sources SET title = 'tampered' WHERE id = :id"),
                    {"id": source["id"]},
                ),
            )
        assert _scalars(
            db_at_0011, "SELECT title FROM report_sources WHERE id = :id", id=source["id"]
        ) == [source["title"]]

    def test_delete_on_report_sources_is_rejected(self, db_at_0011):
        _, startup_id = _insert_founder_with_startup(db_at_0011)
        job_id = _insert_job(db_at_0011, startup_id)
        report = _insert_report(db_at_0011, startup_id, job_id)
        source = _insert_source(db_at_0011, report["id"])
        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            _db(
                db_at_0011,
                lambda conn: conn.execute(
                    sa.text("DELETE FROM report_sources WHERE id = :id"), {"id": source["id"]}
                ),
            )
        assert _scalars(
            db_at_0011, "SELECT count(*) FROM report_sources WHERE id = :id", id=source["id"]
        ) == [1]


def test_downgrade_removes_report_tables_and_preserves_earlier_tables(
    db_at_0011, alembic_config, run_alembic
):
    _, startup_id = _insert_founder_with_startup(db_at_0011)
    job_id = _insert_job(db_at_0011, startup_id)
    _insert_report(db_at_0011, startup_id, job_id)

    async def seed(conn):
        await conn.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {SENTINEL_TABLE} (id int)"))

    _db(db_at_0011, seed)
    try:
        run_alembic(command.downgrade, alembic_config, "0010_analysis_jobs")

        (reports_reg,) = _scalars(db_at_0011, "SELECT to_regclass('public.analysis_reports')")
        assert reports_reg is None, "downgrade must drop the analysis_reports table"
        (sources_reg,) = _scalars(db_at_0011, "SELECT to_regclass('public.report_sources')")
        assert sources_reg is None, "downgrade must drop the report_sources table"
        assert _scalars(
            db_at_0011,
            "SELECT count(*) FROM pg_proc WHERE proname = 'analysis_report_block_mutation'",
        ) == [0], "downgrade must drop the immutability trigger function"

        assert _scalars(
            db_at_0011, "SELECT count(*) FROM startups WHERE id = :id", id=str(startup_id)
        ) == [1], "downgrade must preserve startups"
        assert _scalars(
            db_at_0011, "SELECT count(*) FROM analysis_jobs WHERE id = :id", id=str(job_id)
        ) == [1], "downgrade must preserve analysis_jobs"
        (sentinel,) = _scalars(db_at_0011, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0011, "SELECT version_num FROM alembic_version") == [
            "0010_analysis_jobs"
        ]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")

        async def cleanup(conn):
            await conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}"))

        _db(db_at_0011, cleanup)


def test_head_is_0011(alembic_head):
    assert alembic_head == "0011_analysis_reports"
