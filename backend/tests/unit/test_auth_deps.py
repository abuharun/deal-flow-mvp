"""Auth dependency units (Task B4, slice B2): origin model first, bearer later.

The origin model backs the route-level ambient-credential shield on
/auth/refresh and /auth/logout: an Origin header is accepted only when it
parses as a real web origin AND equals one configured frontend origin after
scheme/host/port normalization — never by substring, prefix, or suffix.
"""

import pytest

from app.security.origins import WebOrigin, origin_allowed

ALLOWED = ("http://localhost:5173", "https://app.bevosita.example")


class TestWebOriginParse:
    def test_parses_scheme_host_and_explicit_port(self):
        origin = WebOrigin.parse("http://localhost:5173")
        assert origin == WebOrigin(scheme="http", host="localhost", port=5173)

    def test_default_ports_are_normalized_per_scheme(self):
        assert WebOrigin.parse("https://app.example") == WebOrigin.parse("https://app.example:443")
        assert WebOrigin.parse("http://app.example") == WebOrigin.parse("http://app.example:80")
        assert WebOrigin.parse("https://app.example") != WebOrigin.parse("https://app.example:80")

    def test_scheme_and_host_are_case_normalized(self):
        assert WebOrigin.parse("HTTPS://APP.Example") == WebOrigin.parse("https://app.example")

    @pytest.mark.parametrize(
        "bad",
        [
            None,
            123,
            "",
            "null",
            "https://",
            "ftp://app.example",
            "ws://app.example",
            "https://app.example/",
            "https://app.example/path",
            "https://app.example?x=1",
            "https://app.example#frag",
            "https://user@app.example",
            "https://user:pass@app.example",
            "https://app.example:not-a-port",
            "https://app.example:99999",
            "https://app.example\n",
            "https://app .example",
            "https://app.example\x00",
            "https://app.example https://other.example",
            "https://a.example,https://b.example",
            "x" * 1000,
        ],
    )
    def test_rejects_anything_that_is_not_a_bare_web_origin(self, bad):
        assert WebOrigin.parse(bad) is None


class TestOriginAllowed:
    def test_exact_configured_origins_are_allowed(self):
        for entry in ALLOWED:
            assert origin_allowed(entry, ALLOWED)

    def test_normalized_variants_of_configured_origins_are_allowed(self):
        assert origin_allowed("HTTP://LOCALHOST:5173", ALLOWED)
        assert origin_allowed("https://app.bevosita.example:443", ALLOWED)

    @pytest.mark.parametrize(
        "evil",
        [
            None,
            "",
            "null",
            "https://evil.example",
            "http://localhost:5174",
            "http://localhost:51730",
            "http://localhost",
            "https://localhost:5173",
            "http://localhost:5173.evil.example",
            "https://app.bevosita.example.evil.example",
            "https://evil.example/https://app.bevosita.example",
            "https://xapp.bevosita.example",
            "https://app.bevosita.example:8443",
            "http://app.bevosita.example",
        ],
    )
    def test_no_substring_prefix_suffix_or_scheme_bypass(self, evil):
        assert not origin_allowed(evil, ALLOWED)

    def test_empty_allowlist_allows_nothing(self):
        assert not origin_allowed("https://app.bevosita.example", ())


# --- Bearer principal dependencies (slice 2) ---------------------------------

import dataclasses  # noqa: E402
import uuid  # noqa: E402

from app.deps import Principal, extract_bearer_token, require_role  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.models import User, UserRole  # noqa: E402

TOKEN = "eyJhbGciOiJIUzI1NiJ9.payload.signature"


def _make_principal(role: UserRole) -> Principal:
    user = User(
        id=uuid.uuid4(),
        email="principal@example.com",
        password_hash="secret-hash-value",
        full_name="Principal User",
        role=role,
    )
    return Principal(user_id=user.id, role=role, user=user)


class TestExtractBearerToken:
    def test_extracts_the_single_token_from_a_well_formed_header(self):
        assert extract_bearer_token(f"Bearer {TOKEN}") == TOKEN

    @pytest.mark.parametrize("scheme", ["bearer", "BEARER", "BeArEr"])
    def test_scheme_matching_is_case_insensitive(self, scheme):
        assert extract_bearer_token(f"{scheme} {TOKEN}") == TOKEN

    @pytest.mark.parametrize(
        "header",
        [
            None,
            "",
            TOKEN,
            "Bearer",
            "Bearer ",
            f"Bearer  {TOKEN}",
            f" Bearer {TOKEN}",
            f"Bearer {TOKEN} ",
            f"Bearer {TOKEN} extra",
            f"Bearer {TOKEN},{TOKEN}",
            f"Bearer {TOKEN}, Bearer {TOKEN}",
            f"Basic {TOKEN}",
            f"Bearer{TOKEN}",
            "Bearer bad token",
            f"Bearer {TOKEN}\n",
            "Bearer tok\x00en",
            'Bearer "quoted"',
        ],
    )
    def test_rejects_missing_malformed_or_multiple_credentials(self, header):
        assert extract_bearer_token(header) is None


class TestPrincipal:
    def test_principal_is_frozen(self):
        principal = _make_principal(UserRole.FOUNDER)
        with pytest.raises(dataclasses.FrozenInstanceError):
            principal.role = UserRole.VC

    def test_repr_leaks_neither_user_row_nor_secrets(self):
        principal = _make_principal(UserRole.FOUNDER)
        assert "secret-hash-value" not in repr(principal)
        assert "principal@example.com" not in repr(principal)


class TestRequireRole:
    async def test_matching_role_passes_the_principal_through(self):
        principal = _make_principal(UserRole.VC)
        assert await require_role(UserRole.VC)(principal) is principal
        assert await require_role(UserRole.FOUNDER, UserRole.VC)(principal) is principal

    @pytest.mark.parametrize(
        ("granted", "required"),
        [(UserRole.FOUNDER, UserRole.VC), (UserRole.VC, UserRole.FOUNDER)],
    )
    async def test_wrong_role_raises_forbidden_role(self, granted, required):
        principal = _make_principal(granted)
        with pytest.raises(ApiError) as excinfo:
            await require_role(required)(principal)
        assert excinfo.value.status_code == 403
        assert excinfo.value.code == "FORBIDDEN_ROLE"
