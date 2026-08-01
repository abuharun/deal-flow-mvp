"""VC-owner invitations (Task B2).

Mirrors Alembic revision 0003_invites; keep the two in sync. Only the SHA-256
hash of the invite token is stored — the raw token exists solely in the
activation URL handed to the inviter.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Text, func, text
from sqlalchemy.dialects.postgresql import BYTEA, CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (
        # Non-unique: re-inviting the same email issues a fresh token.
        Index("ix_invites_email", "email"),
        # Expiry sweeps scan by expires_at.
        Index("ix_invites_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(BYTEA(), unique=True, nullable=False)
    created_by: Mapped[str] = mapped_column(Text(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
