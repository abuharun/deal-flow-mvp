"""Application settings: safe local defaults, fail-fast validation in production."""

import ipaddress
import re
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Hard ceiling on estimated per-run AI cost, independent of anything an
# operator sets: analysis_max_cost_usd may only ever tighten this, never
# loosen it. Mirrors app.models.analysis_job.MAX_COST_ESTIMATE_USD (not
# imported directly, to keep config.py free of any app.models dependency).
_MAX_ANALYSIS_COST_USD = Decimal("0.25")
_MAX_OPENAI_PROMPT_VERSION_LENGTH = 32
# The only report schema this codebase can validate/persist today (see
# app.models.analysis_report.SCHEMA_VERSION_REPORT_V1 and
# app.schemas.report.ReportV1Input.schema_version, which is pinned to the
# same literal). Not imported directly for the same reason as above; kept in
# lockstep by the cross-check in tests/unit/test_config.py.
SUPPORTED_REPORT_SCHEMA_VERSIONS = ("report.v1",)

# Wording that marks a secret as a stand-in rather than a provisioned value.
_PLACEHOLDER_MARKERS = ("change", "placeholder", "example", "dummy", "local", "dev-")
_MIN_PROD_JWT_SECRET_LENGTH = 64
_ASYNC_PG_PREFIX = "postgresql+asyncpg://"
# Lightweight shape check; the real proof of a sender is Resend domain verification.
_EMAIL_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Resend's shared test sender: fine for console/resend_test, never for production sends.
_RESEND_ONBOARDING_SENDER = "onboarding@resend.dev"
# Characters that can smuggle headers, HTML, or extra URL parts into anything
# built from a public URL (verification emails, CORS): never valid in ours.
_URL_FORBIDDEN_CHARS = re.compile(r"[\s\x00-\x1f\x7f\"'<>\\`]")


def _split_public_url(field_name: str, value: str, *, require_https: bool):
    """Parse-and-reject validation for URLs we later embed in emails and CORS.

    Error messages name the field but never echo the value: a rejected URL can
    carry userinfo credentials that must not land in logs.
    """
    if not value or _URL_FORBIDDEN_CHARS.search(value):
        raise ValueError(
            f"{field_name} must be a non-empty URL without whitespace, control, or quote characters"
        )
    try:
        parts = urlsplit(value)
        hostname, username, password = parts.hostname, parts.username, parts.password
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a parseable URL") from exc
    allowed_schemes = ("https",) if require_https else ("http", "https")
    if parts.scheme not in allowed_schemes:
        raise ValueError(f"{field_name} must be an {' or '.join(allowed_schemes)} URL")
    if not hostname:
        raise ValueError(f"{field_name} must include a hostname")
    if username is not None or password is not None:
        raise ValueError(f"{field_name} must not contain userinfo credentials")
    if parts.query or parts.fragment:
        raise ValueError(f"{field_name} must not contain a query or fragment")
    return parts


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"))

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://bevosita:bevosita@localhost:5432/bevosita"
    jwt_secret: str = "local-dev-jwt-secret-never-use-in-production"
    frontend_origins: Annotated[tuple[str, ...], NoDecode] = ("http://localhost:5173",)
    # Empty by default: no proxy header is ever trusted unless the deployer
    # lists the proxies' CIDRs explicitly (see app.security.client_ip).
    trusted_proxy_cidrs: Annotated[tuple[str, ...], NoDecode] = ()
    api_public_url: str = "http://localhost:8000"
    frontend_public_url: str = "http://localhost:5173"
    email_mode: Literal["console", "resend_test", "resend_prod"] = "console"
    resend_api_key: str | None = None
    email_from: str = _RESEND_ONBOARDING_SENDER
    resend_test_recipient: str | None = None

    # OpenAI analysis-worker config: every field here is optional with a safe
    # default so the WEB API can construct Settings and start with zero AI
    # config. Only the worker's explicit startup check (see
    # app.services.analysis_worker_config.require_worker_config) requires the
    # key and pricing to be present -- never this class's validators, and
    # never _fail_fast_in_production below.
    openai_api_key: str | None = None
    openai_analysis_model: str = "gpt-4o-mini"
    openai_prompt_version: str = "analysis.v1"
    openai_request_timeout_seconds: float = 60.0
    openai_max_output_tokens: int = 4000
    openai_input_price_per_million_usd: Decimal | None = None
    openai_output_price_per_million_usd: Decimal | None = None
    # Conservative, explicitly configured flat charge for the ONE web_search
    # tool enablement per attempt (the tool may run several internal
    # searches; this is a single flat estimate for that whole call, not
    # per-search) -- required at worker startup alongside the token prices,
    # see require_worker_config.
    openai_web_search_cost_usd: Decimal | None = None
    # Pinned to the one schema this codebase currently validates/persists
    # (see SUPPORTED_REPORT_SCHEMA_VERSIONS above); rejects any other value
    # up front rather than allowing silent schema drift between the worker's
    # request and app.schemas.report.ReportV1Input.
    openai_report_schema_version: str = "report.v1"
    analysis_max_cost_usd: Decimal = _MAX_ANALYSIS_COST_USD

    @field_validator("openai_report_schema_version")
    @classmethod
    def _supported_report_schema_version(cls, value: str) -> str:
        if value not in SUPPORTED_REPORT_SCHEMA_VERSIONS:
            raise ValueError(
                "openai_report_schema_version must be one of "
                f"{SUPPORTED_REPORT_SCHEMA_VERSIONS}, got {value!r}"
            )
        return value

    @field_validator("openai_web_search_cost_usd")
    @classmethod
    def _bounded_web_search_cost(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (value < 0 or value > _MAX_ANALYSIS_COST_USD):
            raise ValueError(
                f"openai_web_search_cost_usd must be >= 0 and <= {_MAX_ANALYSIS_COST_USD}"
            )
        return value

    @field_validator("openai_prompt_version")
    @classmethod
    def _bounded_openai_prompt_version(cls, value: str) -> str:
        if not value or len(value) > _MAX_OPENAI_PROMPT_VERSION_LENGTH:
            raise ValueError(
                f"openai_prompt_version must be 1..{_MAX_OPENAI_PROMPT_VERSION_LENGTH} characters"
            )
        return value

    @field_validator("openai_request_timeout_seconds")
    @classmethod
    def _positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("openai_request_timeout_seconds must be positive")
        return value

    @field_validator("openai_max_output_tokens")
    @classmethod
    def _positive_max_output_tokens(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("openai_max_output_tokens must be positive")
        return value

    @field_validator("openai_input_price_per_million_usd", "openai_output_price_per_million_usd")
    @classmethod
    def _non_negative_price(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("openai per-million price must not be negative")
        return value

    @field_validator("analysis_max_cost_usd")
    @classmethod
    def _bounded_analysis_max_cost_usd(cls, value: Decimal) -> Decimal:
        if value <= 0 or value > _MAX_ANALYSIS_COST_USD:
            raise ValueError(f"analysis_max_cost_usd must be > 0 and <= {_MAX_ANALYSIS_COST_USD}")
        return value

    @field_validator("frontend_origins", "trusted_proxy_cidrs", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def _valid_proxy_cidrs(cls, cidrs: tuple[str, ...]) -> tuple[str, ...]:
        for entry in cidrs:
            try:
                ipaddress.ip_network(entry)
            except ValueError as exc:
                raise ValueError(
                    "trusted_proxy_cidrs entries must be valid IP networks or addresses"
                ) from exc
        return cidrs

    @field_validator("frontend_origins")
    @classmethod
    def _no_wildcard_origin(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        if any("*" in origin for origin in origins):
            raise ValueError("frontend_origins must never contain a wildcard origin")
        return origins

    @model_validator(mode="after")
    def _reject_test_sender_for_real_sends(self) -> "Settings":
        # resend_prod means real recipients in any env; the shared onboarding
        # sender is a Resend sandbox address and must never front those sends.
        if self.email_mode == "resend_prod" and self.email_from.lower() == (
            _RESEND_ONBOARDING_SENDER
        ):
            raise ValueError("email_from must be a verified sender when email_mode=resend_prod")
        return self

    @model_validator(mode="after")
    def _validate_public_urls(self) -> "Settings":
        # HTTP (localhost) is tolerated outside production only; the structural
        # checks (userinfo, query, fragment, injection chars) apply everywhere.
        require_https = self.env == "production"
        _split_public_url("api_public_url", self.api_public_url, require_https=require_https)
        _split_public_url(
            "frontend_public_url", self.frontend_public_url, require_https=require_https
        )
        for origin in self.frontend_origins:
            parts = _split_public_url("frontend_origins", origin, require_https=require_https)
            if parts.path:
                raise ValueError("frontend_origins must be bare origins without a path")
        return self

    @model_validator(mode="after")
    def _fail_fast_in_production(self) -> "Settings":
        if self.env != "production":
            return self
        self._require_strong_jwt_secret()
        self._require_origins_present()
        self._require_asyncpg_database_url()
        self._require_sensible_email_from()
        self._require_real_resend_api_key()
        return self

    def _require_strong_jwt_secret(self) -> None:
        secret = self.jwt_secret
        if len(secret) < _MIN_PROD_JWT_SECRET_LENGTH:
            raise ValueError(
                f"jwt_secret must be at least {_MIN_PROD_JWT_SECRET_LENGTH} characters "
                "in production"
            )
        lowered = secret.lower()
        if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
            raise ValueError("jwt_secret looks like a placeholder; set a real secret in production")

    def _require_origins_present(self) -> None:
        if not self.frontend_origins:
            raise ValueError("frontend_origins must list explicit origins in production")

    def _require_asyncpg_database_url(self) -> None:
        if not self.database_url.startswith(_ASYNC_PG_PREFIX):
            raise ValueError(f"database_url must start with {_ASYNC_PG_PREFIX} in production")

    def _require_sensible_email_from(self) -> None:
        if not _EMAIL_ADDRESS.match(self.email_from):
            raise ValueError(f"email_from must be a real email address, got: {self.email_from!r}")

    def _require_real_resend_api_key(self) -> None:
        if self.email_mode == "console":
            return
        key = self.resend_api_key
        if not key:
            raise ValueError(f"resend_api_key is required when email_mode={self.email_mode}")
        lowered = key.lower()
        if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
            raise ValueError("resend_api_key looks like a placeholder; set a real key")
