"""Append-only audit trail writes (Task B2).

Security contract:
- Metadata is recursively redacted with the same sensitive-key policy as the
  logging pipeline before anything reaches the session; the caller's dict is
  never mutated.
- Flushes but never commits: the caller owns the transaction boundary, so an
  audit row and the action it describes commit (or roll back) together.
"""

import re
import uuid
from collections.abc import Mapping
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_setup import redact_sensitive
from app.models import AuditActorType, AuditLog

# Dot-namespaced, e.g. "cli.create_invite" — see the action catalogue in the plan.
_ACTION_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
MAX_ACTION_LENGTH = 128
MAX_ENTITY_TYPE_LENGTH = 64


async def write_audit(
    session: AsyncSession,
    *,
    actor_type: AuditActorType,
    action: str,
    entity_type: str,
    actor_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    metadata: Mapping[str, object] | None = None,
    ip: str | None = None,
    at: datetime | None = None,
) -> AuditLog:
    """Stage one sanitized audit row; validation fails before anything is added.

    `at` is injectable for deterministic tests; omitted, the DB stamps now().
    """
    if len(action) > MAX_ACTION_LENGTH or not _ACTION_PATTERN.match(action):
        raise ValueError(
            "audit action must be dot-namespaced lowercase "
            f"(max {MAX_ACTION_LENGTH} chars), got: {action!r}"
        )
    if not entity_type or len(entity_type) > MAX_ENTITY_TYPE_LENGTH:
        raise ValueError(
            f"audit entity_type must be 1..{MAX_ENTITY_TYPE_LENGTH} chars, got: {entity_type!r}"
        )

    entry = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_=redact_sensitive(dict(metadata or {})),
        ip=ip,
    )
    if at is not None:
        entry.at = at
    session.add(entry)
    await session.flush()
    return entry
