"""Consent data access: append-only grants, one row per startup/kind/version.

Concurrency note: callers mutate consent only after locking the parent
startup row with `_load_owned_startup(..., for_update=True)`, so a plain
check-then-insert in the service is race-safe for the same startup; the
UNIQUE (startup_id, kind, text_version) constraint remains a defence-in-depth
backstop.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Consent


async def get(
    session: AsyncSession, *, startup_id: uuid.UUID, kind: str, text_version: str
) -> Consent | None:
    stmt = select(Consent).where(
        Consent.startup_id == startup_id,
        Consent.kind == kind,
        Consent.text_version == text_version,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_startup(session: AsyncSession, *, startup_id: uuid.UUID) -> list[Consent]:
    stmt = (
        select(Consent)
        .where(Consent.startup_id == startup_id)
        .order_by(Consent.granted_at, Consent.id)
    )
    return list((await session.execute(stmt)).scalars())
