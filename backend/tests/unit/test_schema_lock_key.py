"""Deterministic, credential-free advisory-lock key derivation.

Contracts under test:
- Two pytest processes pointed at the same database must derive the same
  lock key even when their URLs differ in credentials, driver suffix,
  default-port spelling, or host casing — otherwise they would not contend
  and the schema race returns.
- Different databases/hosts/ports must not share a key, or unrelated
  suites would serialize.
- The identity string used for keying (and thus anything derived from it,
  including diagnostics) must never contain URL credentials.
- Keys must fit PostgreSQL's signed 64-bit advisory-lock keyspace and be
  stable across processes (content hash, not Python's salted hash()).
"""

from _schema_lock import advisory_lock_key, database_identity

BASE_URL = "postgresql+asyncpg://alice:s3cret@Db.Example.com:5432/bevosita_test"


def test_key_ignores_credentials():
    other = "postgresql+asyncpg://bob:hunter2@db.example.com:5432/bevosita_test"
    assert advisory_lock_key(BASE_URL) == advisory_lock_key(other)


def test_key_ignores_driver_variant():
    plain = "postgresql://alice:s3cret@db.example.com:5432/bevosita_test"
    assert advisory_lock_key(BASE_URL) == advisory_lock_key(plain)


def test_key_normalizes_default_port_and_host_case():
    no_port = "postgresql+asyncpg://alice:s3cret@DB.EXAMPLE.COM/bevosita_test"
    assert advisory_lock_key(BASE_URL) == advisory_lock_key(no_port)


def test_key_differs_for_other_database_host_and_port():
    assert advisory_lock_key(BASE_URL) != advisory_lock_key(
        "postgresql+asyncpg://alice:s3cret@db.example.com:5432/other_db"
    )
    assert advisory_lock_key(BASE_URL) != advisory_lock_key(
        "postgresql+asyncpg://alice:s3cret@other.example.com:5432/bevosita_test"
    )
    assert advisory_lock_key(BASE_URL) != advisory_lock_key(
        "postgresql+asyncpg://alice:s3cret@db.example.com:5433/bevosita_test"
    )


def test_identity_contains_no_credentials():
    identity = database_identity(BASE_URL)
    assert "alice" not in identity
    assert "s3cret" not in identity
    assert identity == "db.example.com:5432/bevosita_test"


def test_key_is_signed_64bit_and_deterministic():
    key = advisory_lock_key(BASE_URL)
    assert -(2**63) <= key < 2**63
    assert key == advisory_lock_key(BASE_URL)


def test_namespace_isolates_keys():
    # Self-tests take a namespaced key so they can never deadlock against
    # the suite's own autouse lock on the same database.
    assert advisory_lock_key(BASE_URL) != advisory_lock_key(BASE_URL, namespace="self-test")
