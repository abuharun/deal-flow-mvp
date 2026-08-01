"""One private pitch-deck PDF per startup.

Mirrors Alembic revision 0008_pitch_decks; keep the two in sync.

Privacy contract: `content` holds the founder's private PDF bytes. It is a
deferred column so ORM loads never fetch it implicitly — only the authorized
download path may ask for it, and it must never reach logs, audits, error
payloads, or metadata responses.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, UUID
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.models import Base

MAX_DECK_BYTES = 5 * 1024 * 1024  # exactly 5 MiB
MAX_DECK_PAGES = 15
MAX_FILENAME_LENGTH = 255
DECK_MIME_TYPE = "application/pdf"


class PitchDeck(Base):
    __tablename__ = "pitch_decks"
    __table_args__ = (
        # Exactly one deck per startup; replacement rewrites this row.
        UniqueConstraint("startup_id", name="uq_pitch_decks_startup_id"),
        CheckConstraint(
            f"char_length(filename) BETWEEN 1 AND {MAX_FILENAME_LENGTH}",
            name="ck_pitch_decks_filename_length",
        ),
        CheckConstraint(f"mime_type = '{DECK_MIME_TYPE}'", name="ck_pitch_decks_mime_type"),
        CheckConstraint(
            f"size_bytes BETWEEN 1 AND {MAX_DECK_BYTES}", name="ck_pitch_decks_size_bytes"
        ),
        CheckConstraint(
            "size_bytes = octet_length(content)", name="ck_pitch_decks_size_matches_content"
        ),
        CheckConstraint("octet_length(sha256) = 32", name="ck_pitch_decks_sha256_length"),
        CheckConstraint(
            f"page_count BETWEEN 1 AND {MAX_DECK_PAGES}", name="ck_pitch_decks_page_count"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text(), nullable=False)
    mime_type: Mapped[str] = mapped_column(Text(), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    sha256: Mapped[bytes] = mapped_column(BYTEA(), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    # Deferred: never loaded unless explicitly undeferred by the download path.
    content: Mapped[bytes] = deferred(mapped_column(BYTEA(), nullable=False))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
