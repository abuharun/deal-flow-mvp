"""Cross-process serialization of schema-mutating test suites.

Why this exists: two pytest processes sharing one TEST_DATABASE_URL race —
migration tests in one process downgrade/drop users/auth_sessions/
email_tokens while integration tests in the other are using them
(UndefinedTable, stale enum OIDs). A PostgreSQL session-level advisory
lock keyed by the target database's identity makes whole pytest processes
take turns instead.

The key is derived from host:port/dbname only — never credentials — so any
process pointed at the same database contends for the same key, including
across containers/hosts that share the Postgres server. Session-level
advisory locks are dropped automatically when the holding connection dies,
so a killed pytest process can never leave the suite wedged. No database
objects are created, and the lock lives on one dedicated connection that
is separate from every application/SQLAlchemy pool.

pytest-xdist note: each xdist worker is its own process and would take
this same lock, fully serializing workers against a shared database (safe
but slow). The suite does not use xdist today; point each worker at its
own database before adopting it.
"""

import asyncio
import hashlib
import threading

import asyncpg
from sqlalchemy.engine.url import make_url

DEFAULT_TIMEOUT_SECONDS = 600.0
_SUITE_NAMESPACE = "bevosita-test-schema-lock"


def database_identity(url: str) -> str:
    """Credential-free identity of the database `url` points at."""
    parsed = make_url(url)
    host = (parsed.host or "localhost").lower()
    port = parsed.port or 5432
    return f"{host}:{port}/{parsed.database or ''}"


def advisory_lock_key(url: str, namespace: str = _SUITE_NAMESPACE) -> int:
    """Deterministic signed 64-bit pg_advisory_lock key for a database."""
    material = f"{namespace}\x00{database_identity(url)}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big", signed=True)


class SchemaLock:
    """PostgreSQL session-level advisory lock on a dedicated connection.

    The connection lives on a private event-loop thread so the lock's
    lifetime matches this object's lifetime — independent of pytest's or
    the application's event loops — and so acquire/release stay plain
    blocking calls usable from sync fixtures and helper threads.
    """

    def __init__(
        self,
        url: str,
        *,
        key: int | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._url = make_url(url)
        self.key = advisory_lock_key(url) if key is None else key
        self._timeout = timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._conn: asyncpg.Connection | None = None
        self._state_guard = threading.Lock()

    def acquire(self) -> None:
        """Block until the lock is ours, bounded by a server-side timeout."""
        with self._state_guard:
            if self._conn is not None:
                raise RuntimeError("schema lock is already held by this object")
            self._ensure_loop()
            self._conn = self._call(self._acquire_async(), self._timeout + 60)

    def try_acquire(self) -> bool:
        """Take the lock only if it is free; never waits."""
        with self._state_guard:
            if self._conn is not None:
                raise RuntimeError("schema lock is already held by this object")
            self._ensure_loop()
            conn = self._call(self._try_acquire_async(), 60)
            self._conn = conn
            return conn is not None

    def release(self) -> None:
        """Idempotent. Closing the connection drops the lock server-side,
        so even a failed close cannot strand the lock once the process
        (and with it this socket) goes away."""
        with self._state_guard:
            conn, self._conn = self._conn, None
            loop, self._loop = self._loop, None
            thread, self._thread = self._thread, None
        if loop is None:
            return
        if conn is not None:
            try:
                asyncio.run_coroutine_threadsafe(conn.close(), loop).result(timeout=30)
            except Exception:
                pass
        loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=30)
            if not thread.is_alive():
                loop.close()

    def _ensure_loop(self) -> None:
        if self._loop is not None:
            return
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, name="test-schema-lock", daemon=True)
        thread.start()
        self._loop = loop
        self._thread = thread

    def _call(self, coro, timeout: float):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            raise self._timeout_error() from None

    def _timeout_error(self) -> TimeoutError:
        # Deliberately omit every part of the database identity. Even a
        # credential-free database name can equal (or contain) a credential.
        return TimeoutError(
            f"timed out after {self._timeout:.0f}s waiting for the test schema "
            "lock; another pytest process is likely running "
            "schema-mutating tests against this database"
        )

    async def _connect(self) -> asyncpg.Connection:
        return await asyncpg.connect(
            host=self._url.host or "localhost",
            port=self._url.port or 5432,
            user=self._url.username,
            password=self._url.password,
            database=self._url.database,
            timeout=30,
        )

    async def _acquire_async(self) -> asyncpg.Connection:
        conn = await self._connect()
        try:
            await conn.execute(f"SET lock_timeout = {max(1, int(self._timeout * 1000))}")
            await conn.execute("SELECT pg_advisory_lock($1)", self.key)
        except asyncpg.exceptions.LockNotAvailableError:
            await conn.close()
            raise self._timeout_error() from None
        except BaseException:
            await conn.close()
            raise
        return conn

    async def _try_acquire_async(self) -> asyncpg.Connection | None:
        conn = await self._connect()
        try:
            granted = await conn.fetchval("SELECT pg_try_advisory_lock($1)", self.key)
        except BaseException:
            await conn.close()
            raise
        if granted:
            return conn
        await conn.close()
        return None
