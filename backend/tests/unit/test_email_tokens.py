"""Pure email-token behavior (Task B3, slice A) — no DB, no IO.

Email tokens reuse the invite-token hashing principles (256-bit URL-safe
plaintext, SHA-256 at rest, constant-time verification) but live in their own
explicit domain: purposes, TTLs and storage are email-token specific.
"""

import base64
import hashlib
import re

from app.models.email_token import EmailTokenPurpose
from app.services.email_token_service import (
    generate_email_token,
    hash_email_token,
    verify_email_token,
)

URL_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


def _decoded_bytes(token: str) -> bytes:
    # Displayed tokens carry no padding; restore it only to measure entropy.
    return base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))


class TestEmailTokenPurpose:
    def test_purposes_are_exactly_verify_and_reset(self):
        assert {member.value for member in EmailTokenPurpose} == {"verify", "reset"}

    def test_members_are_addressable_by_name(self):
        assert EmailTokenPurpose.VERIFY.value == "verify"
        assert EmailTokenPurpose.RESET.value == "reset"


class TestGenerateEmailToken:
    def test_token_is_url_safe_without_padding(self):
        token = generate_email_token()
        assert URL_SAFE_TOKEN.fullmatch(token), token
        assert "=" not in token

    def test_token_carries_at_least_256_bits_of_entropy(self):
        assert len(_decoded_bytes(generate_email_token())) >= 32

    def test_tokens_are_unique_across_calls(self):
        tokens = {generate_email_token() for _ in range(100)}
        assert len(tokens) == 100


class TestHashEmailToken:
    def test_hash_is_exactly_sha256_raw_bytes_of_the_token(self):
        token = generate_email_token()
        digest = hash_email_token(token)
        assert isinstance(digest, bytes)
        assert len(digest) == 32
        assert digest == hashlib.sha256(token.encode("ascii")).digest()

    def test_hash_is_deterministic_for_the_same_token(self):
        token = generate_email_token()
        assert hash_email_token(token) == hash_email_token(token)

    def test_hash_differs_for_different_tokens(self):
        assert hash_email_token(generate_email_token()) != hash_email_token(generate_email_token())

    def test_token_is_not_recoverable_from_stored_hash(self):
        token = generate_email_token()
        digest = hash_email_token(token)
        assert token.encode("ascii") not in digest
        # Fixed-width output regardless of input: the hash leaks no structure.
        assert len(hash_email_token("x")) == len(digest) == 32


class TestVerifyEmailToken:
    def test_correct_token_verifies_true(self):
        token = generate_email_token()
        assert verify_email_token(token, hash_email_token(token)) is True

    def test_wrong_token_verifies_false(self):
        stored = hash_email_token(generate_email_token())
        assert verify_email_token(generate_email_token(), stored) is False

    def test_malformed_display_tokens_return_false_without_raising(self):
        stored = hash_email_token(generate_email_token())
        for malformed in ("", " ", "not base64 !!", "с-кириллицей", "a" * 10_000, "\x00\n"):
            assert verify_email_token(malformed, stored) is False, repr(malformed)
