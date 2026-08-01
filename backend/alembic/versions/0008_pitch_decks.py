"""pitch_decks: one private founder pitch-deck PDF per startup

Revision ID: 0008_pitch_decks
Revises: 0007_startups
Create Date: 2026-08-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_pitch_decks"
down_revision: str | None = "0007_startups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAX_DECK_BYTES = 5 * 1024 * 1024  # exactly 5 MiB


def upgrade() -> None:
    op.create_table(
        "pitch_decks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # UNIQUE: exactly one deck per startup; replacement rewrites this row.
        sa.Column(
            "startup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("startups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", postgresql.BYTEA(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        # Private bytes: application queries must project explicit metadata
        # columns and only ever SELECT content for the authorized download.
        sa.Column("content", postgresql.BYTEA(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("startup_id", name="uq_pitch_decks_startup_id"),
        # Defence in depth: the API validates first, but a bug or a raw write
        # must still be unable to persist an out-of-contract deck.
        sa.CheckConstraint(
            "char_length(filename) BETWEEN 1 AND 255", name="ck_pitch_decks_filename_length"
        ),
        sa.CheckConstraint("mime_type = 'application/pdf'", name="ck_pitch_decks_mime_type"),
        sa.CheckConstraint(
            f"size_bytes BETWEEN 1 AND {MAX_DECK_BYTES}", name="ck_pitch_decks_size_bytes"
        ),
        sa.CheckConstraint(
            "size_bytes = octet_length(content)", name="ck_pitch_decks_size_matches_content"
        ),
        sa.CheckConstraint("octet_length(sha256) = 32", name="ck_pitch_decks_sha256_length"),
        sa.CheckConstraint("page_count BETWEEN 1 AND 15", name="ck_pitch_decks_page_count"),
    )


def downgrade() -> None:
    op.drop_table("pitch_decks")
