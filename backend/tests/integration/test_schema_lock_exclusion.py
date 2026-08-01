"""Cross-process schema lock: mutual exclusion on real PostgreSQL.

Contracts under test:
- While one holder owns the schema lock, a contender on a second dedicated
  connection cannot enter (pg_locks shows it blocked/refused), and it
  enters promptly once the holder releases. Proven with events and pg_locks
  state, never with sleep-based "did not happen yet" thresholds.
- A contender's bounded wait fails with a generic diagnostic that carries
  no URL, username, or password.
- The suite's autouse session lock is actually granted for this pytest
  process, keyed by the shared TEST_DATABASE_URL identity.

All tests use a namespaced key distinct from the suite's own autouse lock,
so they cannot deadlock against it.
"""

import asyncio
import threading

import pytest
import sqlalchemy as sa
from _schema_lock import SchemaLock, advisory_lock_key
from sqlalchemy.ext.asyncio import create_async_engine

SELF_TEST_NAMESPACE = "bevosita-schema-lock-self-test"


def _advisory_lock_grants(database_url: str, key: int) -> list[bool]:
    """granted flags of every session holding or awaiting the advisory key."""
    classid = (key >> 32) & 0xFFFFFFFF
    objid = key & 0xFFFFFFFF

    async def go() -> list[bool]:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    sa.text(
                        "SELECT granted FROM pg_locks "
                        "WHERE locktype = 'advisory' "
                        f"AND classid = {classid}::oid AND objid = {objid}::oid "
                        "AND objsubid = 1"
                    )
                )
                return [row[0] for row in result]
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _wait_for(predicate, timeout: float = 30.0, interval: float = 0.2) -> bool:
    waited = 0.0
    while waited <= timeout:
        if predicate():
            return True
        threading.Event().wait(interval)
        waited += interval
    return False


def test_contender_cannot_try_acquire_while_held(test_database_url):
    key = advisory_lock_key(test_database_url, namespace=SELF_TEST_NAMESPACE)
    holder = SchemaLock(test_database_url, key=key)
    contender = SchemaLock(test_database_url, key=key)
    try:
        holder.acquire()
        assert contender.try_acquire() is False
        holder.release()
        assert contender.try_acquire() is True
    finally:
        holder.release()
        contender.release()


def test_blocking_contender_enters_only_after_release(test_database_url):
    key = advisory_lock_key(test_database_url, namespace=SELF_TEST_NAMESPACE + "-blocking")
    holder = SchemaLock(test_database_url, key=key)
    contender = SchemaLock(test_database_url, key=key, timeout=120)
    entered = threading.Event()
    failures: list[BaseException] = []

    def contend() -> None:
        try:
            contender.acquire()
            entered.set()
        except BaseException as exc:  # noqa: BLE001 - surfaced via `failures`
            failures.append(exc)

    holder.acquire()
    thread = threading.Thread(target=contend)
    try:
        thread.start()
        # Deterministic "is blocked" proof: Postgres itself reports the
        # contender's ungranted wait on the key before we release.
        assert _wait_for(lambda: False in _advisory_lock_grants(test_database_url, key)), (
            "contender never showed up as waiting in pg_locks"
        )
        assert not entered.is_set(), "contender entered while holder owned the lock"

        holder.release()
        assert entered.wait(timeout=60), "contender did not enter after release"
        assert not failures
    finally:
        holder.release()
        contender.release()
        thread.join(timeout=60)


def test_bounded_wait_diagnostic_leaks_no_credentials(test_database_url):
    key = advisory_lock_key(test_database_url, namespace=SELF_TEST_NAMESPACE + "-timeout")
    holder = SchemaLock(test_database_url, key=key)
    contender = SchemaLock(test_database_url, key=key, timeout=2)
    try:
        holder.acquire()
        with pytest.raises(TimeoutError) as excinfo:
            contender.acquire()
        message = str(excinfo.value)
        url = sa.engine.url.make_url(test_database_url)
        assert "schema lock" in message
        assert test_database_url not in message
        for secret in (url.username, url.password):
            if secret:
                assert secret not in message
    finally:
        holder.release()
        contender.release()


def test_suite_schema_lock_is_held_for_this_process(test_database_url):
    # The autouse session fixture must already hold the (un-namespaced)
    # suite lock; a second pytest process against the same database would
    # queue behind it instead of racing the schema.
    key = advisory_lock_key(test_database_url)
    assert True in _advisory_lock_grants(test_database_url, key)
