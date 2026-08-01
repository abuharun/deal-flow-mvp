"""Append-only audit trail (Task B2).

Mirrors Alembic revision 0004_audit_log; keep the two in sync. Rows are
immutable at the database level (trigger rejects UPDATE/DELETE), and
`metadata` is sanitized by audit_service before it ever reaches a session.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Text, func, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base
from app.models.user import pg_enum


class AuditActorType(enum.Enum):
    USER = "user"
    CLI = "cli"
    WORKER = "worker"
    SYSTEM = "system"


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        # Timeline queries scan by time; entity history by (entity_type, entity_id).
        Index("ix_audit_at", "at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_type: Mapped[AuditActorType] = mapped_column(
        pg_enum(AuditActorType, "audit_actor_type"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text(), nullable=False)
    entity_type: Mapped[str] = mapped_column(Text(), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # "metadata" is reserved on Declarative classes; the column keeps the name.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB(), nullable=False, server_default=text("'{}'::jsonb")
    )
    ip: Mapped[str | None] = mapped_column(INET())
