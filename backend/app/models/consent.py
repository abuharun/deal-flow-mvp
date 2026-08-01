"""Explicit, versioned AI/privacy consent grants — per startup, append-only.

Mirrors Alembic revision 0009_payment_consent; keep the two in sync.

Contract: consent is scoped to a STARTUP, never a blanket founder-level
grant, so a founder who owns several startups grants (or withholds) consent
independently for each one. Rows are append-only — granting again at an
already-granted (startup, kind, text_version) is idempotent (same row), and
a new text_version is a brand-new grant that never deletes or mutates an
earlier version's row, preserving the full consent history. There is no
revoke.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

CONSENT_KIND_AI_PRIVACY = "ai_privacy"
CURRENT_AI_PRIVACY_VERSION = "ai-privacy.v1"
MAX_TEXT_VERSION_LENGTH = 32


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (
        Index("ix_consents_startup", "startup_id"),
        # Same startup/kind/version can never be granted twice; a different
        # text_version is a distinct row so history is preserved.
        UniqueConstraint(
            "startup_id", "kind", "text_version", name="uq_consents_startup_kind_version"
        ),
        CheckConstraint(f"kind = '{CONSENT_KIND_AI_PRIVACY}'", name="ck_consents_kind"),
        CheckConstraint(
            f"char_length(text_version) BETWEEN 1 AND {MAX_TEXT_VERSION_LENGTH}",
            name="ck_consents_text_version_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False
    )
    founder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text(), nullable=False)
    text_version: Mapped[str] = mapped_column(Text(), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
