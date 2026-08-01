"""Pure token behavior for invite tokens (Task B2, slice 1) — no DB, no IO."""

import base64
import hashlib
import re
from urllib.parse import parse_qs, quote, urlsplit

from app.services.invite_service import (
    build_activation_url,
    generate_invite_token,
    hash_invite_token,
    verify_invite_token,
)

URL_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


def _decoded_bytes(token: str) -> bytes:
    # Displayed tokens carry no padding; restore it only to measure entropy.
    return base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))


class TestGenerateInviteToken:
    def test_token_is_url_safe_without_padding(self):
        token = generate_invite_token()
        assert URL_SAFE_TOKEN.fullmatch(token), token
        assert "=" not in token

    def test_token_carries_at_least_256_bits_of_entropy(self):
        assert len(_decoded_bytes(generate_invite_token())) >= 32

    def test_tokens_are_unique_across_calls(self):
        tokens = {generate_invite_token() for _ in range(100)}
        assert len(tokens) == 100


class TestHashInviteToken:
    def test_hash_is_exactly_sha256_of_the_token(self):
        token = generate_invite_token()
        digest = hash_invite_token(token)
        assert isinstance(digest, bytes)
        assert len(digest) == 32
        assert digest == hashlib.sha256(token.encode("ascii")).digest()

    def test_hash_is_deterministic_for_the_same_token(self):
        token = generate_invite_token()
        assert hash_invite_token(token) == hash_invite_token(token)

    def test_hash_differs_for_different_tokens(self):
        assert hash_invite_token(generate_invite_token()) != hash_invite_token(
            generate_invite_token()
        )

    def test_token_is_not_recoverable_from_stored_hash(self):
        token = generate_invite_token()
        digest = hash_invite_token(token)
        assert token.encode("ascii") not in digest
        # Fixed-width output regardless of input: the hash leaks no structure.
        assert len(hash_invite_token("x")) == len(digest) == 32


class TestVerifyInviteToken:
    def test_correct_token_verifies_true(self):
        token = generate_invite_token()
        assert verify_invite_token(token, hash_invite_token(token)) is True

    def test_wrong_token_verifies_false(self):
        stored = hash_invite_token(generate_invite_token())
        assert verify_invite_token(generate_invite_token(), stored) is False

    def test_malformed_display_tokens_return_false_without_raising(self):
        stored = hash_invite_token(generate_invite_token())
        for malformed in ("", " ", "not base64 !!", "с-кириллицей", "a" * 10_000, "\x00\n"):
            assert verify_invite_token(malformed, stored) is False, repr(malformed)


class TestBuildActivationUrl:
    BASE = "https://app.example.com"

    def test_uses_explicit_base_or_settings_api_public_url(self):
        from app.config import Settings

        token = generate_invite_token()
        assert build_activation_url(self.BASE, token).startswith(f"{self.BASE}/")
        settings = Settings()
        url = build_activation_url(settings.api_public_url, token)
        assert url.startswith(f"{settings.api_public_url.rstrip('/')}/")

    def test_no_duplicate_slash_regardless_of_trailing_slash_on_base(self):
        token = generate_invite_token()
        url = build_activation_url(f"{self.BASE}/", token)
        assert url == build_activation_url(self.BASE, token)
        assert "//" not in url.removeprefix("https://")

    def test_token_appears_only_as_the_single_token_query_value(self):
        token = generate_invite_token()
        parts = urlsplit(build_activation_url(self.BASE, token))
        assert parse_qs(parts.query, strict_parsing=True) == {"token": [token]}
        for component in (parts.scheme, parts.netloc, parts.path, parts.fragment):
            assert token not in component
        assert build_activation_url(self.BASE, token).count(token) == 1

    def test_query_parameter_is_percent_safe(self):
        # Real tokens are URL-safe already; the builder must still never emit
        # reserved characters raw if handed something wider.
        hostile = "a b/c&d=e?f#g+h%i"
        parts = urlsplit(build_activation_url(self.BASE, hostile))
        assert parse_qs(parts.query, strict_parsing=True) == {"token": [hostile]}
        assert quote(hostile, safe="") in parts.query
