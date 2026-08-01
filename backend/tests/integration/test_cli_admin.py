"""Administrative CLI (`python -m app.cli`) against real Postgres (Task B2, slice 3).

Contracts under test:
- create-invite prints the one-time activation URL exactly once; the DB holds
  only the SHA-256 of the token; an audit row commits atomically with the invite.
- create-vc-owner prompts (hidden) for the password, creates a verified vc
  user, and commits atomically with its audit row.
- No secret — password, hashes, raw token, DSN, JWT secret — ever reaches
  stdout or audit metadata; failures exit nonzero without a stack trace.

Audit rows created here stay behind on purpose: the table is append-only at
the DB level, so tests clean up only their invite/user rows (unique emails).
"""

import asyncio
import hashlib
import json
import re
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from typer.testing import CliRunner

from app.cli import app
from app.security.passwords import MIN_PASSWORD_LENGTH, verify_password
from app.services.invite_service import verify_invite_token

runner = CliRunner()

GOOD_PASSWORD = "correct-horse-battery"
ACTIVATION_BASE = "https://bevosita.example.com"


def _unique_email() -> str:
    return f"cli-admin-{uuid.uuid4().hex}@example.com"


def _db(database_url: str, fn):
    async def go():
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as conn:
                return await fn(conn)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _rows(database_url: str, query: str, **params) -> list[dict]:
    async def fn(conn):
        result = await conn.execute(sa.text(query), params)
        return [dict(row) for row in result.mappings()]

    return _db(database_url, fn)


def _audit_rows(database_url: str, entity_id) -> list[dict]:
    return _rows(
        database_url,
        "SELECT actor_type, action, entity_type, entity_id, "
        "CAST(metadata AS text) AS metadata "
        "FROM audit_log WHERE entity_id = :entity_id",
        entity_id=entity_id,
    )


@pytest.fixture()
def cli_env(monkeypatch, test_database_url, db_at_head):
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("ENV", "test")
    return test_database_url


@pytest.fixture()
def cleanup(cli_env):
    emails: list[str] = []
    yield emails

    async def fn(conn):
        for email in emails:
            await conn.execute(
                sa.text("DELETE FROM invites WHERE email = :email"), {"email": email}
            )
            await conn.execute(sa.text("DELETE FROM users WHERE email = :email"), {"email": email})

    _db(cli_env, fn)


def _invoke_create_invite(email: str, *extra: str):
    return runner.invoke(
        app,
        [
            "create-invite",
            "--email",
            email,
            "--created-by",
            "cli:harun",
            "--activation-base-url",
            ACTIVATION_BASE,
            *extra,
        ],
    )


def _invoke_create_vc_owner(email: str, *extra: str, password: str = GOOD_PASSWORD):
    return runner.invoke(
        app,
        ["create-vc-owner", "--email", email, "--full-name", "Laylo Karimova", *extra],
        input=f"{password}\n{password}\n",
    )


def test_create_invite_prints_url_once_and_db_stores_only_hash(cli_env, cleanup):
    email = _unique_email()
    cleanup.append(email)
    result = _invoke_create_invite(email)

    assert result.exit_code == 0, result.output
    tokens = re.findall(r"token=([A-Za-z0-9_\-%]+)", result.output)
    assert len(tokens) == 1, "the activation URL (and token) must be printed exactly once"
    token = tokens[0]
    assert result.output.count(token) == 1
    assert f"{ACTIVATION_BASE}/activate?token={token}" in result.output

    (row,) = _rows(
        cli_env,
        "SELECT id, token_hash, created_by, expires_at, used_at FROM invites WHERE email = :email",
        email=email,
    )
    assert verify_invite_token(token, row["token_hash"]), "URL token must match the stored hash"
    assert row["token_hash"] == hashlib.sha256(token.encode("ascii")).digest()
    assert row["created_by"] == "cli:harun"
    assert row["used_at"] is None

    # Nothing secret in the output: no hash, no DSN, no JWT secret.
    assert row["token_hash"].hex() not in result.output
    assert "postgresql" not in result.output
    assert "bevosita:bevosita" not in result.output
    assert "jwt" not in result.output.lower()


def test_create_invite_writes_committed_sanitized_audit_row(cli_env, cleanup):
    email = _unique_email()
    cleanup.append(email)
    result = _invoke_create_invite(email)
    assert result.exit_code == 0, result.output

    token = re.findall(r"token=([A-Za-z0-9_\-%]+)", result.output)[0]
    (invite,) = _rows(cli_env, "SELECT id FROM invites WHERE email = :email", email=email)
    (audit,) = _audit_rows(cli_env, invite["id"])
    assert audit["actor_type"] == "cli"
    assert audit["action"] == "cli.create_invite"
    assert audit["entity_type"] == "invite"
    assert token not in audit["metadata"], "raw token must never reach audit metadata"
    metadata = json.loads(audit["metadata"])
    assert metadata["email"] == email


def test_create_invite_honours_expires_days(cli_env, cleanup):
    email = _unique_email()
    cleanup.append(email)
    result = _invoke_create_invite(email, "--expires-days", "3")
    assert result.exit_code == 0, result.output

    (row,) = _rows(
        cli_env,
        "SELECT (expires_at - now()) AS remaining FROM invites WHERE email = :email",
        email=email,
    )
    assert 2.9 < row["remaining"].total_seconds() / 86400 <= 3.0


def test_create_invite_rejects_invalid_email_without_touching_db(cli_env):
    result = _invoke_create_invite("not-an-email")
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert _rows(cli_env, "SELECT id FROM invites WHERE email = 'not-an-email'") == []


def test_create_invite_rolls_back_invite_when_audit_write_fails(cli_env, cleanup, monkeypatch):
    async def explode(*args, **kwargs):
        raise RuntimeError("audit insert forced to fail")

    monkeypatch.setattr("app.services.audit_service.write_audit", explode)
    email = _unique_email()
    cleanup.append(email)
    result = _invoke_create_invite(email)

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "token=" not in result.output, "no activation URL may leak from a failed run"
    assert _rows(cli_env, "SELECT id FROM invites WHERE email = :email", email=email) == [], (
        "invite and audit row must commit atomically: audit failure rolls back the invite"
    )


def test_create_vc_owner_creates_verified_vc_user_with_hashed_password(cli_env, cleanup):
    email = _unique_email()
    cleanup.append(email)
    result = _invoke_create_vc_owner(email)

    assert result.exit_code == 0, result.output
    (row,) = _rows(
        cli_env,
        "SELECT id, password_hash, full_name, CAST(role AS text) AS role, "
        "CAST(locale AS text) AS locale, email_verified_at FROM users WHERE email = :email",
        email=email,
    )
    assert row["role"] == "vc"
    assert row["locale"] == "uz"
    assert row["full_name"] == "Laylo Karimova"
    assert row["email_verified_at"] is not None, "the CLI-created owner is pre-verified"
    assert row["email_verified_at"].tzinfo is not None
    assert verify_password(GOOD_PASSWORD, row["password_hash"])

    # Confirmation of identity only — never the password, its hash, or the DSN.
    assert email in result.output
    assert str(row["id"]) in result.output
    assert GOOD_PASSWORD not in result.output
    assert row["password_hash"] not in result.output
    assert "postgresql" not in result.output
    assert "bevosita:bevosita" not in result.output


def test_create_vc_owner_supports_ru_locale(cli_env, cleanup):
    email = _unique_email()
    cleanup.append(email)
    result = _invoke_create_vc_owner(email, "--locale", "ru")
    assert result.exit_code == 0, result.output
    (row,) = _rows(
        cli_env,
        "SELECT CAST(locale AS text) AS locale FROM users WHERE email = :email",
        email=email,
    )
    assert row["locale"] == "ru"


def test_create_vc_owner_writes_committed_audit_row_without_password(cli_env, cleanup):
    email = _unique_email()
    cleanup.append(email)
    result = _invoke_create_vc_owner(email)
    assert result.exit_code == 0, result.output

    (user,) = _rows(
        cli_env, "SELECT id, password_hash FROM users WHERE email = :email", email=email
    )
    (audit,) = _audit_rows(cli_env, user["id"])
    assert audit["actor_type"] == "cli"
    assert audit["action"] == "cli.create_vc_owner"
    assert audit["entity_type"] == "user"
    assert GOOD_PASSWORD not in audit["metadata"]
    assert user["password_hash"] not in audit["metadata"]
    assert json.loads(audit["metadata"])["email"] == email


def test_create_vc_owner_duplicate_email_fails_safely(cli_env, cleanup):
    email = _unique_email()
    cleanup.append(email)
    first = _invoke_create_vc_owner(email)
    assert first.exit_code == 0, first.output

    second = _invoke_create_vc_owner(email)
    assert second.exit_code != 0
    assert "Traceback" not in second.output
    assert GOOD_PASSWORD not in second.output
    assert len(_rows(cli_env, "SELECT id FROM users WHERE email = :email", email=email)) == 1


def test_create_vc_owner_rejects_short_password(cli_env, cleanup):
    email = _unique_email()
    cleanup.append(email)
    short = "x" * (MIN_PASSWORD_LENGTH - 1)
    result = _invoke_create_vc_owner(email, password=short)

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert short not in result.output
    assert _rows(cli_env, "SELECT id FROM users WHERE email = :email", email=email) == []


def test_create_vc_owner_never_accepts_password_as_option(cli_env, cleanup):
    email = _unique_email()
    cleanup.append(email)
    result = runner.invoke(
        app,
        [
            "create-vc-owner",
            "--email",
            email,
            "--full-name",
            "Laylo Karimova",
            "--password",
            GOOD_PASSWORD,
        ],
    )
    assert result.exit_code != 0, "--password must not exist; prompts only"
    assert _rows(cli_env, "SELECT id FROM users WHERE email = :email", email=email) == []


def test_create_vc_owner_rolls_back_user_when_audit_write_fails(cli_env, cleanup, monkeypatch):
    async def explode(*args, **kwargs):
        raise RuntimeError("audit insert forced to fail")

    monkeypatch.setattr("app.services.audit_service.write_audit", explode)
    email = _unique_email()
    cleanup.append(email)
    result = _invoke_create_vc_owner(email)

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert GOOD_PASSWORD not in result.output
    assert _rows(cli_env, "SELECT id FROM users WHERE email = :email", email=email) == [], (
        "user and audit row must commit atomically: audit failure rolls back the user"
    )
