"""Application settings: safe local defaults, fail-fast validation in production."""

import ipaddress
import re
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

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
