"""Async database foundation and readiness probing."""

from collections.abc import Awaitable, Callable
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent

ReadinessProbe = Callable[[], Awaitable[None]]


class NotReadyError(Exception):
    """Service must answer /readyz with 503. `detail` is safe to show clients."""

    detail = "not_ready"


class DatabaseUnreachableError(NotReadyError):
    detail = "database_unreachable"


class MigrationsOutOfDateError(NotReadyError):
    detail = "migrations_out_of_date"


def build_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, connect_args={"timeout": 5})


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def alembic_script_head() -> str:
    """Head revision from the migration scripts on disk — no subprocess."""
    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if head is None:
        raise RuntimeError("no alembic head revision found in the scripts directory")
    return head


def build_readiness_probe(engine: AsyncEngine, expected_head: str) -> ReadinessProbe:
    async def probe() -> None:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                table = await conn.execute(text("SELECT to_regclass('public.alembic_version')"))
                if table.scalar() is None:
                    raise MigrationsOutOfDateError
                version = (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one_or_none()
        except NotReadyError:
            raise
        except Exception as exc:
            # The client-facing detail must never carry DSNs, credentials, or
            # driver exception text — swallow everything but the safe marker.
            raise DatabaseUnreachableError from exc
        if version != expected_head:
            raise MigrationsOutOfDateError

    return probe
