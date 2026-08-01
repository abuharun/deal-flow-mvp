"""Migration tests for revision 0010_analysis_jobs against real Postgres.

analysis_jobs stores at most one current AI-analysis job per startup
(UNIQUE startup_id FK, ON DELETE CASCADE), tied to the exact input_revision
of the startup at trigger time. Defence-in-depth CHECKs enforce: status is
one of queued/running/retrying/completed/failed, attempts >= 0,
max_attempts in 1..3, started_at/finished_at track status coherently,
model/prompt_version are bounded when present, tokens are non-negative,
cost_estimate_usd is between 0 and 0.25, and last_error_code/message_key
are bounded, fixed-charset (never free text).

Downgrade must remove exactly this table and leave every earlier table
(users, startups, submissions, pitch_decks, payments, consents, ...)
untouched.
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

SENTINEL_TABLE = "b10_analysis_jobs_sentinel"


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
    email = f"analysisjob-{uuid.uuid4().hex}@example.com"

    async def fn(conn):
        founder_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role) "
                    "VALUES (:email, 'x', 'Analysis Owner', 'founder') RETURNING id"
                ),
                {"email": email},
            )
        ).scalar_one()
        startup_id = (
            await conn.execute(
                sa.text(
                    "INSERT INTO startups (founder_id, name) "
                    "VALUES (:founder_id, 'Analysis Startup') RETURNING id"
                ),
                {"founder_id": str(founder_id)},
            )
        ).scalar_one()
        return founder_id, startup_id

    return _db(database_url, fn)


def _insert_job(database_url: str, startup_id: uuid.UUID, **overrides):
    values = {"startup_id": str(startup_id), "input_revision": 1}
    values.update(overrides)
    # Raw SQL expressions (e.g. now()) are inlined directly; asyncpg cannot
    # bind a TextClause as a parameter value.
    raw_sql = {k: v.text for k, v in values.items() if isinstance(v, sa.sql.elements.TextClause)}
    bound = {k: v for k, v in values.items() if k not in raw_sql}
    columns = ", ".join(values)
    placeholders = ", ".join(raw_sql.get(name, f":{name}") for name in values)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                f"INSERT INTO analysis_jobs ({columns}) VALUES ({placeholders}) "
                "RETURNING id, startup_id, input_revision, status, attempts, max_attempts, "
                "queued_at, started_at, finished_at, model, prompt_version, input_tokens, "
                "output_tokens, cost_estimate_usd, last_error_code, last_error_message_key"
            ),
            bound,
        )
        return result.mappings().one()

    return _db(database_url, fn)


@pytest.fixture()
def db_at_0010(alembic_config, run_alembic, test_database_url):
    run_alembic(command.upgrade, alembic_config, "0009_payment_consent")
    run_alembic(command.upgrade, alembic_config, "0010_analysis_jobs")
    yield test_database_url
    run_alembic(command.upgrade, alembic_config, "head")


def test_analysis_jobs_columns_types_nullability_and_defaults(db_at_0010):
    cols = _column_info(db_at_0010, "analysis_jobs")
    expected = {
        "id": ("uuid", "NO"),
        "startup_id": ("uuid", "NO"),
        "input_revision": ("int4", "NO"),
        "status": ("text", "NO"),
        "attempts": ("int4", "NO"),
        "max_attempts": ("int4", "NO"),
        "queued_at": ("timestamptz", "NO"),
        "started_at": ("timestamptz", "YES"),
        "heartbeat_at": ("timestamptz", "YES"),
        "finished_at": ("timestamptz", "YES"),
        "deadline_at": ("timestamptz", "YES"),
        "next_attempt_at": ("timestamptz", "YES"),
        "model": ("text", "YES"),
        "prompt_version": ("text", "YES"),
        "input_tokens": ("int4", "YES"),
        "output_tokens": ("int4", "YES"),
        "cost_estimate_usd": ("numeric", "YES"),
        "last_error_code": ("text", "YES"),
        "last_error_message_key": ("text", "YES"),
        "created_at": ("timestamptz", "NO"),
        "updated_at": ("timestamptz", "NO"),
    }
    assert set(cols) == set(expected)
    for name, (udt, nullable) in expected.items():
        assert cols[name]["udt_name"] == udt, name
        assert cols[name]["is_nullable"] == nullable, name
    assert "gen_random_uuid()" in cols["id"]["column_default"]
    assert "queued" in cols["status"]["column_default"]
    assert cols["attempts"]["column_default"] == "0"
    assert cols["max_attempts"]["column_default"] == "3"
    assert "now()" in cols["queued_at"]["column_default"]


def test_valid_queued_job_roundtrips(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    job = _insert_job(db_at_0010, startup_id)
    assert isinstance(job["id"], uuid.UUID)
    assert job["status"] == "queued"
    assert job["attempts"] == 0
    assert job["max_attempts"] == 3
    assert job["started_at"] is None
    assert job["finished_at"] is None


def test_startup_id_is_unique_one_current_job_per_startup(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    _insert_job(db_at_0010, startup_id)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id)


def test_job_is_deleted_with_its_startup(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    job = _insert_job(db_at_0010, startup_id)
    _db(
        db_at_0010,
        lambda conn: conn.execute(
            sa.text("DELETE FROM startups WHERE id = :id"), {"id": str(startup_id)}
        ),
    )
    assert _scalars(
        db_at_0010, "SELECT count(*) FROM analysis_jobs WHERE id = :id", id=job["id"]
    ) == [0]


def test_orphan_job_is_rejected(db_at_0010):
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, uuid.uuid4())


def test_input_revision_must_be_at_least_1(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, input_revision=0)


@pytest.mark.parametrize("status", ["pending", "done", "PAUSED", ""])
def test_status_must_be_one_of_the_canonical_values(db_at_0010, status):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, status=status)


def test_attempts_cannot_be_negative(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, attempts=-1)


@pytest.mark.parametrize("max_attempts", [0, 4])
def test_max_attempts_must_be_between_1_and_3(db_at_0010, max_attempts):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, max_attempts=max_attempts)


def test_queued_status_forbids_started_at(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, status="queued", started_at=sa.text("now()"))


def test_running_status_requires_started_at(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, status="running")


def test_valid_running_job_roundtrips(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                "INSERT INTO analysis_jobs (startup_id, input_revision, status, started_at) "
                "VALUES (:startup_id, 1, 'running', now()) RETURNING status, started_at"
            ),
            {"startup_id": str(startup_id)},
        )
        return result.mappings().one()

    job = _db(db_at_0010, fn)
    assert job["status"] == "running"
    assert job["started_at"] is not None


def test_completed_status_requires_finished_at(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, status="completed", started_at=sa.text("now()"))


def test_valid_completed_job_roundtrips(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)

    async def fn(conn):
        result = await conn.execute(
            sa.text(
                "INSERT INTO analysis_jobs "
                "(startup_id, input_revision, status, started_at, finished_at) "
                "VALUES (:startup_id, 1, 'completed', now(), now()) "
                "RETURNING status, started_at, finished_at"
            ),
            {"startup_id": str(startup_id)},
        )
        return result.mappings().one()

    job = _db(db_at_0010, fn)
    assert job["status"] == "completed"
    assert job["finished_at"] is not None


@pytest.mark.parametrize("model_value", ["", "x" * 129])
def test_model_length_must_be_1_to_128_chars_when_present(db_at_0010, model_value):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, model=model_value)


@pytest.mark.parametrize("prompt_version", ["", "x" * 33])
def test_prompt_version_length_must_be_1_to_32_chars_when_present(db_at_0010, prompt_version):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, prompt_version=prompt_version)


def test_input_tokens_cannot_be_negative(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, input_tokens=-1)


def test_output_tokens_cannot_be_negative(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, output_tokens=-1)


@pytest.mark.parametrize("cost", ["-0.01", "0.26", "1.00"])
def test_cost_estimate_must_be_between_0_and_0_25(db_at_0010, cost):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, cost_estimate_usd=cost)


def test_cost_estimate_of_0_25_is_accepted(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    job = _insert_job(db_at_0010, startup_id, cost_estimate_usd="0.25")
    assert job["cost_estimate_usd"] is not None


@pytest.mark.parametrize("code", ["", "lowercase", "x" * 65, "HAS SPACE", "HAS-DASH"])
def test_last_error_code_must_be_bounded_uppercase_when_present(db_at_0010, code):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, last_error_code=code)


def test_last_error_code_accepts_valid_value(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    job = _insert_job(db_at_0010, startup_id, last_error_code="PROVIDER_TIMEOUT")
    assert job["last_error_code"] == "PROVIDER_TIMEOUT"


@pytest.mark.parametrize(
    "message_key", ["", "NoDotNamespace", "errors", ".errors.leading", "errors."]
)
def test_last_error_message_key_must_match_the_dot_namespaced_pattern(db_at_0010, message_key):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    with pytest.raises(sa.exc.IntegrityError):
        _insert_job(db_at_0010, startup_id, last_error_message_key=message_key)


def test_last_error_message_key_accepts_valid_value(db_at_0010):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    job = _insert_job(db_at_0010, startup_id, last_error_message_key="errors.analysisTimeout")
    assert job["last_error_message_key"] == "errors.analysisTimeout"


def test_downgrade_removes_analysis_jobs_and_preserves_earlier_tables(
    db_at_0010, alembic_config, run_alembic
):
    _, startup_id = _insert_founder_with_startup(db_at_0010)
    _insert_job(db_at_0010, startup_id)

    async def seed(conn):
        await conn.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {SENTINEL_TABLE} (id int)"))

    _db(db_at_0010, seed)
    try:
        run_alembic(command.downgrade, alembic_config, "0009_payment_consent")

        (reg,) = _scalars(db_at_0010, "SELECT to_regclass('public.analysis_jobs')")
        assert reg is None, "downgrade must drop the analysis_jobs table"

        assert _scalars(
            db_at_0010, "SELECT count(*) FROM startups WHERE id = :id", id=str(startup_id)
        ) == [1], "downgrade must preserve startups"
        (sentinel,) = _scalars(db_at_0010, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade must not touch unrelated tables"
        assert _scalars(db_at_0010, "SELECT version_num FROM alembic_version") == [
            "0009_payment_consent"
        ]
    finally:
        run_alembic(command.upgrade, alembic_config, "head")

        async def cleanup(conn):
            await conn.execute(sa.text(f"DROP TABLE IF EXISTS {SENTINEL_TABLE}"))

        _db(db_at_0010, cleanup)
