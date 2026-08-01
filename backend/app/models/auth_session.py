"""Refresh-token sessions (Task B4).

Mirrors Alembic revision 0006_auth_sessions; keep the two in sync. Only the
SHA-256 hash of the refresh token is stored — the raw token exists solely in
the one-time grant handed to its owner. Rows form rotation families
(family_id) sharing one absolute expiry fixed at family creation.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        # Revoke-all-for-user scans by user_id.
        Index("ix_sessions_user", "user_id"),
        # Rotation-reuse revocation touches every row in a family.
        Index("ix_sessions_family", "family_id"),
        # Expiry sweeps scan by expires_at.
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(BYTEA(), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
