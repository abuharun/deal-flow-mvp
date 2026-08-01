"""Argon2id password hashing.

Current parameters (documented so `needs_rehash` semantics are auditable):
time_cost=3, memory_cost=65536 KiB (64 MiB), parallelism=2, salt_len=16,
hash_len=32 — RFC 9106 second recommended profile, sized for a small
Render instance. Raising them later is safe: `needs_rehash` flags old
hashes for transparent upgrade at next successful login.

Never log or persist plaintext passwords; hashes go only to users.password_hash.
"""

from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions

# Bounds Argon2 input cost before any expensive work. Generous for real
# passphrases; callers reject longer input instead of truncating it.
MAX_PASSWORD_BYTES = 1024

# Product-wide floor (plan §5: SecretStr min 10); enforced by every caller
# that accepts a new password (CLI today, signup schema in B3).
MIN_PASSWORD_LENGTH = 10

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    salt_len=16,
    hash_len=32,
)


def _password_too_long(password: str) -> bool:
    return len(password.encode("utf-8")) > MAX_PASSWORD_BYTES


def hash_password(password: str) -> str:
    """Hash a plaintext password with a fresh random salt.

    Raises ValueError for over-limit passwords so signup/reset surface a
    validation error instead of hashing unbounded input.
    """
    if _password_too_long(password):
        raise ValueError(f"password exceeds {MAX_PASSWORD_BYTES} bytes")
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """True only for a well-formed stored hash matching the password.

    Never raises: a malformed or corrupted stored hash — and an over-limit
    candidate, which can never be correct — read as a failed verification.
    """
    if _password_too_long(password):
        return False
    try:
        return _hasher.verify(stored_hash, password)
    except (argon2_exceptions.VerificationError, argon2_exceptions.InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """True when the stored hash predates the current parameters above."""
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except argon2_exceptions.InvalidHashError:
        return True
