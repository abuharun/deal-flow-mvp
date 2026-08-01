import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from _schema_lock import SchemaLock
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _test_database_url() -> str:
    # Real Postgres only — the suite must never silently fall back to SQLite.
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL must be set to a postgresql+asyncpg URL "
            "(e.g. postgresql+asyncpg://bevosita:bevosita@127.0.0.1:5432/bevosita)"
        )
    return url


@pytest.fixture(scope="session", autouse=True)
def _serialize_schema_mutations():
    """Hold the shared database's suite lock for this entire pytest process.

    Session scope plus autouse ensures this is established before any
    function-scoped database or migration fixture can run.
    """
    lock = SchemaLock(_test_database_url())
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


@pytest.fixture()
def test_database_url() -> str:
    return _test_database_url()


@pytest.fixture()
def client_factory():
    @asynccontextmanager
    async def make(database_url: str):
        from app.config import Settings
        from app.main import create_app

        settings = Settings(env="test", database_url=database_url)
        app = create_app(settings)
        # httpx.ASGITransport does not run startup/shutdown; drive the lifespan
        # explicitly so the engine is created and disposed like in production.
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
                yield c

    return make


@pytest.fixture()
async def client(client_factory, test_database_url):
    async with client_factory(test_database_url) as c:
        yield c


def _run_alembic(fn, /, *args, **kwargs):
    # Alembic's env.py drives async migrations with asyncio.run(), which cannot
    # start while the test's event loop is running; a fresh thread has no loop.
    errors: list[BaseException] = []

    def target() -> None:
        try:
            fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised in the test thread
            errors.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]


@pytest.fixture()
def run_alembic():
    return _run_alembic


@pytest.fixture()
def alembic_config(test_database_url) -> AlembicConfig:
    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", test_database_url)
    return cfg


@pytest.fixture()
def alembic_head(alembic_config) -> str:
    head = ScriptDirectory.from_config(alembic_config).get_current_head()
    assert head, "alembic script directory must have a head revision"
    return head


@pytest.fixture()
def db_at_head(alembic_config, run_alembic):
    from alembic import command

    run_alembic(command.upgrade, alembic_config, "head")
