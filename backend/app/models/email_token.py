"""Email verification/reset tokens (Task B3).

Mirrors Alembic revision 0005_email_tokens; keep the two in sync. Only the
SHA-256 hash of the token is stored — the raw token exists solely in the
verification URL emailed to its owner.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base
from app.models.user import pg_enum


class EmailTokenPurpose(enum.Enum):
    VERIFY = "verify"
    RESET = "reset"


class EmailToken(Base):
    __tablename__ = "email_tokens"
    __table_args__ = (
        # "Newest token for this user/purpose" is the hot lookup on issue.
        Index("ix_email_tokens_user_purpose", "user_id", "purpose"),
        # Expiry sweeps scan by expires_at.
        Index("ix_email_tokens_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[EmailTokenPurpose] = mapped_column(
        pg_enum(EmailTokenPurpose, "email_token_purpose"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(BYTEA(), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
