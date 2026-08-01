"""Unit tests for Argon2id password hashing (Task B1, slice 1)."""

import time

import pytest

from app.security.passwords import (
    MAX_PASSWORD_BYTES,
    hash_password,
    needs_rehash,
    verify_password,
)

PASSWORD = "correct horse battery staple"


def test_same_password_hashes_to_different_salted_values():
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)
    assert first != second, "equal hashes would mean a static or missing salt"
    assert verify_password(PASSWORD, first) is True
    assert verify_password(PASSWORD, second) is True


def test_hash_uses_argon2id_variant():
    assert hash_password(PASSWORD).startswith("$argon2id$")


def test_verify_accepts_correct_password():
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_verify_rejects_wrong_password():
    assert verify_password("wrong password entirely", hash_password(PASSWORD)) is False


@pytest.mark.parametrize(
    "malformed",
    [
        "",
        "not-a-hash",
        "$argon2id$garbage",
        "$argon2id$v=19$m=65536,t=3,p=2$truncated",
        "$2b$12$bcrypt-shaped-but-not-argon2..............",
    ],
)
def test_verify_rejects_malformed_stored_hash_without_raising(malformed):
    # A corrupted DB value must read as "wrong password", never as a 500.
    assert verify_password(PASSWORD, malformed) is False


def test_needs_rehash_false_for_current_params():
    assert needs_rehash(hash_password(PASSWORD)) is False


def test_needs_rehash_detects_downgraded_params():
    from argon2 import PasswordHasher

    downgraded = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    assert needs_rehash(downgraded) is True


def test_max_password_bytes_is_explicit_and_sensible():
    # Generous for real passphrases, small enough to bound Argon2 input cost.
    assert 128 <= MAX_PASSWORD_BYTES <= 4096


def test_hash_accepts_password_at_the_byte_limit():
    at_limit = "a" * MAX_PASSWORD_BYTES
    assert verify_password(at_limit, hash_password(at_limit)) is True


def test_hash_rejects_password_over_the_byte_limit():
    with pytest.raises(ValueError):
        hash_password("a" * (MAX_PASSWORD_BYTES + 1))


def test_limit_counts_bytes_not_characters():
    two_byte_char = "ё"  # 2 bytes in UTF-8
    assert len(two_byte_char.encode()) == 2
    ok = two_byte_char * (MAX_PASSWORD_BYTES // 2)
    assert verify_password(ok, hash_password(ok)) is True
    with pytest.raises(ValueError):
        hash_password(two_byte_char * (MAX_PASSWORD_BYTES // 2 + 1))


def test_verify_returns_false_for_over_limit_password_without_raising():
    stored = hash_password(PASSWORD)
    # Login path: an over-limit password can never be correct, and must be
    # refused cheaply (no Argon2 work) instead of raising.
    assert verify_password("a" * (MAX_PASSWORD_BYTES + 1), stored) is False


def test_unicode_password_round_trip():
    password = "pärol–Ózbekiston🔐 оқим sўз"
    stored = hash_password(password)
    assert verify_password(password, stored) is True
    assert verify_password(password + "!", stored) is False


def test_hashing_time_sanity_bound():
    # Generous for slow CI, but pathological params (e.g. GiB-scale memory
    # cost or huge time cost) would blow well past this.
    start = time.perf_counter()
    hash_password(PASSWORD)
    assert time.perf_counter() - start < 2.0
