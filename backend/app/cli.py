"""Administrative CLI (Task B2): run as `python -m app.cli`.

Each command creates its row and its audit entry in one transaction — both
commit or neither does. Secrets never reach stdout/stderr: the activation
URL is printed exactly once (only after commit), passwords are prompted
hidden, and failures exit nonzero with a one-line message instead of a
traceback that could carry a DSN or credential.
"""

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TypeVar

import typer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import build_engine, build_sessionmaker
from app.models import AuditActorType, UiLocale, User, UserRole
from app.security.passwords import MIN_PASSWORD_LENGTH, hash_password

# Imported as modules (not names) so the audit dependency stays patchable in
# tests that force the write to fail.
from app.services import audit_service, invite_service

app = typer.Typer(pretty_exceptions_enable=False)

# Minimal shape check to catch operator typos before touching the database;
# full email schema validation arrives with the signup surface (B3).
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_EMAIL_LENGTH = 254

T = TypeVar("T")


def _validated_email(email: str) -> str:
    if len(email) > _MAX_EMAIL_LENGTH or not _EMAIL_PATTERN.match(email):
        raise typer.BadParameter(f"not a valid email address: {email!r}")
    return email


def _fail(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(1)


async def _in_transaction(database_url: str, fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run `fn` inside a single transaction on a one-shot, always-disposed engine."""
    engine = build_engine(database_url)
    try:
        sessionmaker = build_sessionmaker(engine)
        async with sessionmaker() as session, session.begin():
            return await fn(session)
    finally:
        await engine.dispose()


@app.command("create-invite")
def create_invite(
    email: str = typer.Option(..., "--email"),
    created_by: str = typer.Option(..., "--created-by"),
    activation_base_url: str = typer.Option(..., "--activation-base-url"),
    expires_days: int = typer.Option(14, "--expires-days", min=1),
) -> None:
    """Create a founder invite and print its one-time activation URL."""
    email = _validated_email(email)
    settings = Settings()

    async def create(session: AsyncSession) -> str:
        grant = await invite_service.create_invite(
            session,
            email=email,
            created_by=created_by,
            activation_base_url=activation_base_url,
            expires_in=timedelta(days=expires_days),
        )
        await audit_service.write_audit(
            session,
            actor_type=AuditActorType.CLI,
            action="cli.create_invite",
            entity_type="invite",
            entity_id=grant.invite.id,
            metadata={"email": email, "created_by": created_by, "expires_days": expires_days},
        )
        return grant.activation_url

    try:
        activation_url = asyncio.run(_in_transaction(settings.database_url, create))
    except Exception as exc:
        # Exception text may carry a DSN or driver detail; only the type is safe.
        raise _fail(
            f"could not create the invite ({type(exc).__name__}); nothing was committed"
        ) from None
    # After commit, exactly once — the raw token exists nowhere else.
    typer.echo(f"Invite created for {email}.")
    typer.echo(f"One-time activation URL: {activation_url}")


@app.command("create-vc-owner")
def create_vc_owner(
    email: str = typer.Option(..., "--email"),
    full_name: str = typer.Option(..., "--full-name"),
    locale: str = typer.Option("uz", "--locale"),
) -> None:
    """Create the pre-verified VC owner account (password prompted, never echoed)."""
    email = _validated_email(email)
    try:
        ui_locale = UiLocale(locale)
    except ValueError:
        choices = ", ".join(member.value for member in UiLocale)
        raise typer.BadParameter(f"locale must be one of: {choices}") from None
    # Prompt-only on purpose: a --password option or env var would leak into
    # shell history and process listings.
    password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise _fail(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    try:
        password_hash = hash_password(password)
    except ValueError:
        raise _fail("password is too long") from None
    settings = Settings()

    async def create(session: AsyncSession) -> str:
        user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            role=UserRole.VC,
            locale=ui_locale,
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        await session.flush()
        await audit_service.write_audit(
            session,
            actor_type=AuditActorType.CLI,
            action="cli.create_vc_owner",
            entity_type="user",
            entity_id=user.id,
            metadata={"email": email, "full_name": full_name, "locale": ui_locale.value},
        )
        return str(user.id)

    try:
        user_id = asyncio.run(_in_transaction(settings.database_url, create))
    except IntegrityError:
        raise _fail(f"a user with email {email} already exists") from None
    except Exception as exc:
        raise _fail(
            f"could not create the VC owner ({type(exc).__name__}); nothing was committed"
        ) from None
    typer.echo(f"VC owner created: {email} (id={user_id})")


if __name__ == "__main__":
    app()
