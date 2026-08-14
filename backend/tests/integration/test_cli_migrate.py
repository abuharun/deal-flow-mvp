"""`python -m app.cli migrate` — the Render release/pre-deploy command.

Contracts under test: it drives the database to the Alembic head (from
scratch or when already there), it is safe to run repeatedly, and a failure
never leaks the DSN or driver detail to stdout/stderr.

Sync test functions on purpose: `migrate` calls `alembic.command.upgrade`
synchronously, which drives its own `asyncio.run()` inside env.py — that
cannot nest inside an already-running event loop, so these tests must not be
async (mirrors tests/integration/test_cli_admin.py).
"""

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from typer.testing import CliRunner

from app.cli import app

runner = CliRunner()

# Closed port + fake password, mirroring tests/integration/test_health.py.
UNREACHABLE_URL = "postgresql+asyncpg://bevosita:sekretpw@127.0.0.1:59999/bevosita"


def _invoke_migrate():
    return runner.invoke(app, ["migrate"])


def _current_version(database_url: str) -> str | None:
    async def fn():
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sa.text("SELECT version_num FROM alembic_version"))
                return result.scalar_one_or_none()
        finally:
            await engine.dispose()

    return asyncio.run(fn())


def test_migrate_brings_the_database_to_head(monkeypatch, test_database_url, alembic_head):
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("ENV", "test")

    result = _invoke_migrate()

    assert result.exit_code == 0, result.output
    assert "migrations: up to date" in result.output
    assert _current_version(test_database_url) == alembic_head


def test_migrate_is_idempotent_when_already_at_head(
    monkeypatch, test_database_url, db_at_head, alembic_head
):
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("ENV", "test")

    result = _invoke_migrate()

    assert result.exit_code == 0, result.output
    assert _current_version(test_database_url) == alembic_head


def test_migrate_failure_never_leaks_dsn_or_traceback(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    monkeypatch.setenv("ENV", "test")

    result = _invoke_migrate()

    assert result.exit_code == 1
    for leak in ("sekretpw", "127.0.0.1", "Traceback"):
        assert leak not in result.output
    assert "migration failed" in result.output
