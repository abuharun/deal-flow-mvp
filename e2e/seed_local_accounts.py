"""Seed the two LOCAL-ONLY accounts the browser E2E signs in as.

Run from `backend/` so `app` is importable:

    cd backend && .venv/bin/python ../e2e/seed_local_accounts.py

Safety, in order of how load-bearing it is:

1. It refuses to run when ENV is production, and refuses any database that is
   not on this machine. There is no flag to override either check.
2. The credentials it writes come from `e2e/local-accounts.json`, which is
   throwaway test data checked into the repo precisely so nobody is tempted to
   point this at a real database "just once". They are useless anywhere but a
   developer's own Postgres.
3. It is idempotent and destructive in exactly one direction: the E2E founder's
   startups are deleted (cascading to their decks, payments, consents, jobs,
   reports, narratives, and approvals) so every run starts from the same
   state. It never touches a startup belonging to anyone else.

The accounts are created pre-verified because email verification is a
separate, already-tested surface (tests/integration/test_signup_verify.py);
re-walking it in the browser would only make the E2E slower and flakier
without proving anything the suite does not already prove.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import sqlalchemy as sa

from app.config import Settings
from app.db import build_engine, build_sessionmaker
from app.models import UiLocale, User, UserRole
from app.security.passwords import hash_password

ACCOUNTS_FILE = Path(__file__).resolve().parent / "local-accounts.json"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def _require_local(settings: Settings) -> None:
    if settings.env == "production":
        _fail("refusing to seed test accounts with ENV=production")
    host = urlsplit(settings.database_url).hostname
    if host not in LOCAL_HOSTS:
        _fail(f"refusing to seed test accounts into a non-local database host: {host!r}")


async def _upsert(session, *, email: str, password: str, full_name: str, role: UserRole) -> str:
    existing = (
        await session.execute(sa.select(User).where(User.email == email))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if existing is None:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
            locale=UiLocale.UZ,
            email_verified_at=now,
        )
        session.add(user)
        await session.flush()
        return str(user.id)
    # Re-running must converge on the documented state, not layer onto
    # whatever a previous run (or a manual poke) left behind.
    existing.password_hash = hash_password(password)
    existing.full_name = full_name
    existing.role = role
    existing.email_verified_at = existing.email_verified_at or now
    await session.flush()
    return str(existing.id)


async def main() -> None:
    settings = Settings()
    _require_local(settings)
    accounts = json.loads(ACCOUNTS_FILE.read_text())

    engine = build_engine(settings.database_url)
    try:
        async with build_sessionmaker(engine)() as session, session.begin():
            founder_id = await _upsert(
                session,
                email=accounts["founder"]["email"],
                password=accounts["founder"]["password"],
                full_name=accounts["founder"]["full_name"],
                role=UserRole.FOUNDER,
            )
            vc_id = await _upsert(
                session,
                email=accounts["vc"]["email"],
                password=accounts["vc"]["password"],
                full_name=accounts["vc"]["full_name"],
                role=UserRole.VC,
            )
            removed = await session.execute(
                sa.text("DELETE FROM startups WHERE founder_id = :fid"), {"fid": founder_id}
            )
    finally:
        await engine.dispose()

    print(f"founder {accounts['founder']['email']} ready (id={founder_id})")
    print(f"vc      {accounts['vc']['email']} ready (id={vc_id})")
    print(f"cleared {removed.rowcount} startup(s) from the previous run")


if __name__ == "__main__":
    asyncio.run(main())
