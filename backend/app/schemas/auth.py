"""Request/response contracts for the public auth endpoints (Tasks B3-B4).

Passwords travel as SecretStr so they never appear in reprs or validation
errors; token/name/email fields are length-bounded before any work happens.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.security.passwords import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH

MAX_TOKEN_LENGTH = 512
MAX_FULL_NAME_LENGTH = 200
MAX_EMAIL_LENGTH = 254


def _new_password_within_module_bounds(value: SecretStr) -> SecretStr:
    # The product-wide policy for every freshly chosen password (signup,
    # reset): 10-char floor and the module byte cap, checked before hashing.
    secret = value.get_secret_value()
    if len(secret) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(secret.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must not exceed {MAX_PASSWORD_BYTES} bytes")
    return value


class ActivateInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=MAX_TOKEN_LENGTH)
    email: EmailStr = Field(max_length=MAX_EMAIL_LENGTH)
    password: SecretStr
    full_name: str = Field(min_length=1, max_length=MAX_FULL_NAME_LENGTH)
    locale: Literal["uz", "ru"]

    _password_policy = field_validator("password")(_new_password_within_module_bounds)

    @field_validator("full_name")
    @classmethod
    def _full_name_trimmed_nonempty(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("full_name must not be blank")
        return trimmed


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=MAX_TOKEN_LENGTH)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=MAX_EMAIL_LENGTH)


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=MAX_TOKEN_LENGTH)
    new_password: SecretStr

    _password_policy = field_validator("new_password")(_new_password_within_module_bounds)


class OkResponse(BaseModel):
    ok: Literal[True] = True


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=MAX_EMAIL_LENGTH)
    password: SecretStr

    @field_validator("password")
    @classmethod
    def _password_within_byte_cap(cls, value: SecretStr) -> SecretStr:
        # Login only bounds the input (no minimum-length check): a short
        # password can never verify, and answering 401 instead of 422 keeps
        # every wrong credential on one uniform path.
        secret = value.get_secret_value()
        if not secret:
            raise ValueError("password must not be empty")
        if len(secret.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password must not exceed {MAX_PASSWORD_BYTES} bytes")
        return value


class UserSummary(BaseModel):
    """The safe, public projection of a user — never hashes or tokens."""

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: Literal["founder", "vc"]
    locale: Literal["uz", "ru"]


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserSummary


class AccessTokenResponse(BaseModel):
    """The refresh endpoint's body: just the new access grant, never the user."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
