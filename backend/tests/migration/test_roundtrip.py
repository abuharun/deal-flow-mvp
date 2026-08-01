import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

SENTINEL_TABLE = "b0_roundtrip_sentinel"


def _run_sql(database_url: str, *statements: str) -> list:
    async def go() -> list:
        engine = create_async_engine(database_url)
        results = []
        try:
            async with engine.begin() as conn:
                for stmt in statements:
                    result = await conn.execute(sa.text(stmt))
                    results.append(result.scalar() if result.returns_rows else None)
        finally:
            await engine.dispose()
        return results

    return asyncio.run(go())


def _alembic_version(database_url: str) -> str | None:
    (exists,) = _run_sql(database_url, "SELECT to_regclass('public.alembic_version')")
    if exists is None:
        return None
    (version,) = _run_sql(database_url, "SELECT version_num FROM alembic_version")
    return version


def test_migration_roundtrip_restores_head_and_spares_unrelated_tables(
    alembic_config, alembic_head, run_alembic, test_database_url
):
    # An unrelated table must survive downgrade base: the baseline may only
    # manage its own revision bookkeeping, never the rest of the schema.
    _run_sql(
        test_database_url,
        f"CREATE TABLE IF NOT EXISTS {SENTINEL_TABLE} (id int)",
    )
    try:
        run_alembic(command.upgrade, alembic_config, "head")
        assert _alembic_version(test_database_url) == alembic_head

        run_alembic(command.downgrade, alembic_config, "base")
        assert _alembic_version(test_database_url) is None
        (sentinel,) = _run_sql(test_database_url, f"SELECT to_regclass('public.{SENTINEL_TABLE}')")
        assert sentinel is not None, "downgrade base must not drop unrelated tables"

        run_alembic(command.upgrade, alembic_config, "head")
        assert _alembic_version(test_database_url) == alembic_head
    finally:
        run_alembic(command.upgrade, alembic_config, "head")
        _run_sql(test_database_url, f"DROP TABLE IF EXISTS {SENTINEL_TABLE}")
