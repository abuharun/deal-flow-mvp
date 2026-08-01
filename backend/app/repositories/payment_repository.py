"""Payment data access: one demo/pilot payment row per startup.

Concurrency note: callers mutate a payment only after locking the parent
startup row with `_load_owned_startup(..., for_update=True)` (the same
pattern startup_service and deck_service use), so a plain lookup here is
enough — concurrent writers for the same startup are already serialized by
that lock before this module is ever touched.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment


async def get_for_startup(session: AsyncSession, *, startup_id: uuid.UUID) -> Payment | None:
    stmt = select(Payment).where(Payment.startup_id == startup_id)
    return (await session.execute(stmt)).scalar_one_or_none()
