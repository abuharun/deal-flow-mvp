"""Migration tests for revision 0013_narrative_approvals against real Postgres.

narrative_approvals is the founder's explicit, one-per-startup freeze of the
narrative: it stores no text at all, only WHICH immutable version was
approved, WHO approved it, and WHEN. The approved text is therefore always
the version row it names, and the two can never drift.

Four database-level guarantees are asserted here, because the app layer must
not be the only thing standing between a founder's approved pitch and a
silent rewrite:

1. The approval can only name a version that really belongs to this startup
   AND carries the version number and report the approval claims -- a
   four-column composite FK into narrative_versions (id, startup_id, version,
   report_id) checks the whole identity as one unit, so a row pointing at
   version 3 while claiming to be version 2 is impossible.
2. The approval must name the startup's CURRENT narrative version at insert
   time (BEFORE INSERT trigger against startup_narratives) -- approving is
   defined as freezing what the founder is looking at, never an older
   revision.
3. The approval row itself is immutable: direct UPDATE/DELETE is rejected by
   a trigger (REVOKE cannot bind the table owner, which is who the app
   connects as), while a DELETE cascaded from hard-deleting an owning row is
   still allowed so account deletion stays possible.
4. Once an approval exists the whole narrative is frozen at the database
   level: no new version may be inserted for that startup and its current
   pointer may not move. Other startups are entirely unaffected.

Downgrade must remove exactly this table, its triggers, the freeze triggers
it installed on the 0012 tables, and the identity UNIQUE constraint -- and
leave every earlier table (including narrative_versions rows) untouched.
"""

import asyncio
import json
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

SENTINEL_TABLE = "b13_approvals_sentinel"


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


def _seeded(database_url: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A founder, their startup, and that startup's immutable report."""
    email = f"approval-{uuid.uuid4().hex}@example.com"

    async def fn(conn):
        founder_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role) "
                    "VALUES (:email, 'x', 'Approval Owner', 'founder') RETURNING id"
                ),
                {"email": email},
            )
        ).scalar_one()
        startup_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO startups (founder_id, name) "
                    "VALUES (:founder_id, 'Approval Startup') RETURNING id"
                ),
                {"founder_id": str(founder_id)},
            )
        ).scalar_one()
        job_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO analysis_jobs (startup_id, input_revision) "
                    "VALUES (:startup_id, 1) RETURNING id"
                ),
                {"startup_id": str(startup_id)},
            )
        ).scalar_one()
        report_id = (
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
        return founder_id, startup_id, report_id

    return _db(database_url, fn)


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
        "content": "The narrative the founder is about to approve.",
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
                "RETURNING id, startup_id, version, content, report_id"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


def _set_current(database_url: str, startup_id: uuid.UUID, version: int = 1) -> None:
    async def fn(conn):
        await conn.execute(
            sa.text(
                "INSERT INTO startup_narratives (startup_id, current_version) "
                "VALUES (:startup_id, :version) "
                "ON CONFLICT (startup_id) DO UPDATE SET current_version = :version"
            ),
            {"startup_id": str(startup_id), "version": version},
        )

    _db(database_url, fn)


def _insert_approval(
    database_url: str,
    startup_id: uuid.UUID,
    version_row,
    founder_id: uuid.UUID,
    **overrides,
):
    values = {
        "startup_id": str(startup_id),
        "narrative_version_id": str(version_row["id"]),
        "version": version_row["version"],
        "report_id": str(version_row["report_id"]),
        "approved_by": str(founder_id),
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO narrative_approvals ({columns}) VALUES ({placeholders}) "
                "RETURNING id, startup_id, narrative_version_id, version, report_id, "
                "approved_by, approved_at"
            ),
            values,
        )
        return result.mappings().one()

    return _db(database_url, fn)


def _approved(database_url: str):
    """A founder, startup, report, current version 1, and its approval."""
    founder_id, startup_id, report_id = _seeded(database_url)
    version = _insert_version(database_url, startup_id, report_id, founder_id)
    _set_current(database_url, startup_id, 1)
    approval = _insert_approval(database_url, startup_id, version, founder_id)
    return founder_id, startup_id, report_id, version, approval


@pytest.fixture()
def db_at_0013(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0012_narratives")
    run_alembic(command.upgrade, alembic_config, "0013_narrative_approvals")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


class TestColumnsAndDefaults:
    def test_columns_types_nullability_and_defaults(self, db_at_0013):
        cols = _column_info(db_at_0013, "narrative_approvals")
        expected = {
            "id": ("uuid", "NO"),
            "startup_id": ("uuid", "NO"),
            "narrative_version_id": ("uuid", "NO"),
            "version": ("int4", "NO"),
            "report_id": ("uuid", "NO"),
            "approved_by": ("uuid", "NO"),
            "approved_at": ("timestamptz", "NO"),
        }
        assert set(cols) == set(expected)
        for name, (udt, nullable) in expected.items():
            assert cols[name]["udt_name"] == udt, name
            assert cols[name]["is_nullable"] == nullable, name
        assert "gen_random_uuid()" in cols["id"]["column_default"]
        assert "now()" in cols["approved_at"]["column_default"]

    def test_the_approval_stores_no_narrative_text_of_its_own(self, db_at_0013):
        # The approved narrative IS the immutable version row this names; a
        # copy of the text here could drift from what history says.
        cols = _column_info(db_at_0013, "narrative_approvals")
        assert "content" not in cols


class TestValidRoundtrip:
    def test_valid_approval_roundtrips_with_a_database_stamped_timestamp(self, db_at_0013):
        founder_id, startup_id, report_id = _seeded(db_at_0013)
        version = _insert_version(db_at_0013, startup_id, report_id, founder_id)
        _set_current(db_at_0013, startup_id, 1)

        approval = _insert_approval(db_at_0013, startup_id, version, founder_id)

        assert approval["narrative_version_id"] == version["id"]
        assert approval["version"] == 1
        assert approval["report_id"] == report_id
        assert approval["approved_by"] == founder_id
        assert approval["approved_at"] is not None

    def test_a_later_version_can_be_approved_once_it_is_current(self, db_at_0013):
        founder_id, startup_id, report_id = _seeded(db_at_0013)
        _insert_version(db_at_0013, startup_id, report_id, founder_id, version=1)
        second = _insert_version(
            db_at_0013,
            startup_id,
            report_id,
            founder_id,
            version=2,
            source="founder_edit",
            content="The rewritten narrative.",
        )
        _set_current(db_at_0013, startup_id, 2)

        approval = _insert_approval(db_at_0013, startup_id, second, founder_id)

        assert approval["version"] == 2


class TestForeignKeysAndUniqueness:
    def test_orphan_startup_is_rejected(self, db_at_0013):
        founder_id, startup_id, report_id = _seeded(db_at_0013)
        version = _insert_version(db_at_0013, startup_id, report_id, founder_id)
        _set_current(db_at_0013, startup_id, 1)

        with pytest.raises(sa.exc.DBAPIError):
            _insert_approval(db_at_0013, uuid.uuid4(), version, founder_id)

    def test_orphan_approver_is_rejected(self, db_at_0013):
        founder_id, startup_id, report_id = _seeded(db_at_0013)
        version = _insert_version(db_at_0013, startup_id, report_id, founder_id)
        _set_current(db_at_0013, startup_id, 1)

        with pytest.raises(sa.exc.IntegrityError):
            _insert_approval(
                db_at_0013, startup_id, version, founder_id, approved_by=str(uuid.uuid4())
            )

    def test_only_one_approval_per_startup(self, db_at_0013):
        founder_id, startup_id, _, version, _ = _approved(db_at_0013)

        with pytest.raises(sa.exc.IntegrityError):
            _insert_approval(db_at_0013, startup_id, version, founder_id)

    def test_an_approval_cannot_name_another_startups_version(self, db_at_0013):
        founder_a, startup_a, report_a = _seeded(db_at_0013)
        foreign = _insert_version(db_at_0013, startup_a, report_a, founder_a)
        founder_b, startup_b, report_b = _seeded(db_at_0013)
        _insert_version(db_at_0013, startup_b, report_b, founder_b)
        _set_current(db_at_0013, startup_b, 1)

        with pytest.raises(sa.exc.DBAPIError):
            _insert_approval(db_at_0013, startup_b, foreign, founder_b)

    def test_a_version_id_that_disagrees_with_the_version_number_is_rejected(self, db_at_0013):
        # The composite FK checks (id, startup_id, version, report_id) as one
        # unit: an approval claiming version 1 while pointing at version 2's
        # row could otherwise freeze text nobody approved.
        founder_id, startup_id, report_id = _seeded(db_at_0013)
        _insert_version(db_at_0013, startup_id, report_id, founder_id, version=1)
        second = _insert_version(
            db_at_0013, startup_id, report_id, founder_id, version=2, source="founder_edit"
        )
        _set_current(db_at_0013, startup_id, 1)

        with pytest.raises(sa.exc.IntegrityError):
            _insert_approval(db_at_0013, startup_id, second, founder_id, version=1)

    def test_a_report_id_that_disagrees_with_the_versions_report_is_rejected(self, db_at_0013):
        founder_id, startup_id, report_id = _seeded(db_at_0013)
        _, _, other_report = _seeded(db_at_0013)
        version = _insert_version(db_at_0013, startup_id, report_id, founder_id)
        _set_current(db_at_0013, startup_id, 1)

        with pytest.raises(sa.exc.IntegrityError):
            _insert_approval(
                db_at_0013, startup_id, version, founder_id, report_id=str(other_report)
            )

    def test_the_approval_is_deleted_when_the_startup_is_hard_deleted(self, db_at_0013):
        # A direct DELETE is always rejected, but hard-deleting the owning
        # startup must still cascade -- otherwise account deletion would be
        # impossible once a founder has approved their narrative.
        _, startup_id, _, _, approval = _approved(db_at_0013)

        _db(
            db_at_0013,
            lambda conn: conn.execute(
                sa.text("DELETE FROM startups WHERE id = :id"), {"id": str(startup_id)}
            ),
        )

        assert _scalars(
            db_at_0013, "SELECT count(*) FROM narrative_approvals WHERE id = :id", id=approval["id"]
        ) == [0]


class TestChecks:
    def test_version_must_be_at_least_1(self, db_at_0013):
        founder_id, startup_id, report_id = _seeded(db_at_0013)
        version = _insert_version(db_at_0013, startup_id, report_id, founder_id)
        _set_current(db_at_0013, startup_id, 1)

        with pytest.raises(sa.exc.IntegrityError):
            _insert_approval(db_at_0013, startup_id, version, founder_id, version=0)


class TestApprovalMustFreezeTheCurrentVersion:
    def test_approving_a_version_that_is_not_current_is_rejected(self, db_at_0013):
        founder_id, startup_id, report_id = _seeded(db_at_0013)
        first = _insert_version(db_at_0013, startup_id, report_id, founder_id, version=1)
        _insert_version(
            db_at_0013, startup_id, report_id, founder_id, version=2, source="founder_edit"
        )
        _set_current(db_at_0013, startup_id, 2)

        with pytest.raises(sa.exc.DBAPIError, match="current"):
            _insert_approval(db_at_0013, startup_id, first, founder_id)

    def test_approving_with_no_current_pointer_at_all_is_rejected(self, db_at_0013):
        founder_id, startup_id, report_id = _seeded(db_at_0013)
        version = _insert_version(db_at_0013, startup_id, report_id, founder_id)

        with pytest.raises(sa.exc.DBAPIError, match="current"):
            _insert_approval(db_at_0013, startup_id, version, founder_id)


class TestImmutability:
    def test_update_on_an_approval_is_rejected(self, db_at_0013):
        _, _, _, _, approval = _approved(db_at_0013)

        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            _db(
                db_at_0013,
                lambda conn: conn.execute(
                    sa.text("UPDATE narrative_approvals SET version = 2 WHERE id = :id"),
                    {"id": approval["id"]},
                ),
            )

        assert _scalars(
            db_at_0013, "SELECT version FROM narrative_approvals WHERE id = :id", id=approval["id"]
        ) == [1]

    def test_delete_on_an_approval_is_rejected(self, db_at_0013):
        _, _, _, _, approval = _approved(db_at_0013)

        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            _db(
                db_at_0013,
                lambda conn: conn.execute(
                    sa.text("DELETE FROM narrative_approvals WHERE id = :id"),
                    {"id": approval["id"]},
                ),
            )

        assert _scalars(
            db_at_0013, "SELECT count(*) FROM narrative_approvals WHERE id = :id", id=approval["id"]
        ) == [1]


class TestApprovalFreezesTheNarrative:
    def test_no_new_version_can_be_written_once_the_narrative_is_approved(self, db_at_0013):
        founder_id, startup_id, report_id, _, _ = _approved(db_at_0013)

        with pytest.raises(sa.exc.DBAPIError, match="approved"):
            _insert_version(
                db_at_0013,
                startup_id,
                report_id,
                founder_id,
                version=2,
                source="founder_edit",
                content="Text written after approval.",
            )

        assert _scalars(
            db_at_0013,
            "SELECT count(*) FROM narrative_versions WHERE startup_id = :id",
            id=str(startup_id),
        ) == [1]

    def test_the_current_pointer_cannot_move_once_the_narrative_is_approved(self, db_at_0013):
        founder_id, startup_id, report_id = _seeded(db_at_0013)
        version = _insert_version(db_at_0013, startup_id, report_id, founder_id, version=1)
        _insert_version(
            db_at_0013, startup_id, report_id, founder_id, version=2, source="founder_edit"
        )
        _set_current(db_at_0013, startup_id, 1)
        _insert_approval(db_at_0013, startup_id, version, founder_id)

        with pytest.raises(sa.exc.DBAPIError, match="approved"):
            _set_current(db_at_0013, startup_id, 2)

        assert _scalars(
            db_at_0013,
            "SELECT current_version FROM startup_narratives WHERE startup_id = :id",
            id=str(startup_id),
        ) == [1]

    def test_the_approved_version_keeps_its_exact_text(self, db_at_0013):
        _, startup_id, _, version, _ = _approved(db_at_0013)

        assert _scalars(
            db_at_0013,
            "SELECT content FROM narrative_versions WHERE startup_id = :id",
            id=str(startup_id),
        ) == [version["content"]]

    def test_another_startups_narrative_is_untouched_by_the_freeze(self, db_at_0013):
        _approved(db_at_0013)
        founder_id, startup_id, report_id = _seeded(db_at_0013)
        _insert_version(db_at_0013, startup_id, report_id, founder_id, version=1)
        _set_current(db_at_0013, startup_id, 1)

        _insert_version(
            db_at_0013, startup_id, report_id, founder_id, version=2, source="founder_edit"
        )
        _set_current(db_at_0013, startup_id, 2)

        assert _scalars(
            db_at_0013,
            "SELECT current_version FROM startup_narratives WHERE startup_id = :id",
            id=str(startup_id),
        ) == [2]


def test_downgrade_removes_the_approval_table_and_preserves_earlier_tables(
    db_at_0013, alembic_config, run_alembic
):
    founder_id, startup_id, report_id, version, _ = _approved(db_at_0013)

    async def seed(conn):
        await conn.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {SENTINEL_TABLE} (id int)"))

    _db(db_at_0013, seed)
    try:
        run_alembic(command.downgrade, alembic_config, "0012_narratives")

        (approvals,) = _scalars(db_at_0013, "SELECT to_regclass('public.narrative_approvals')")
        assert approvals is None, "downgrade must drop the narrative_approvals table"
        assert _scalars(
            db_at_0013,
            "SELECT count(*) FROM pg_proc WHERE proname IN "
            "('narrative_approval_block_mutation', 'narrative_approval_current_version', "
            "'narrative_block_after_approval')",
        ) == [0], "downgrade must drop the approval trigger functions"
        assert _scalars(
            db_at_0013,
            "SELECT count(*) FROM pg_constraint WHERE conname = 'uq_narrative_versions_identity'",
        ) == [0], "downgrade must drop the identity constraint it added"

        # The narrative itself must survive, editable again.
        assert _scalars(
            db_at_0013,
            "SELECT content FROM narrative_versions WHERE id = :id",
            id=version["id"],
        ) == [version["content"]]
        _insert_version(
            db_at_0013, startup_id, report_id, founder_id, version=2, source="founder_edit"
        )
        assert _scalars(
            db_at_0013, "SELECT count(*) FROM analysis_reports WHERE id = :id", id=str(report_id)
        ) == [1], "downgrade must preserve analysis_reports"
        (sentinel,) = _scalars(db_at_0013, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0013, "SELECT version_num FROM alembic_version") == [
            "0012_narratives"
        ]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")

        async def cleanup(conn):
            await conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}"))

        _db(db_at_0013, cleanup)


def test_head_is_0013(alembic_head):
    assert alembic_head == "0013_narrative_approvals"
