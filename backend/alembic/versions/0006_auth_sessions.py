"""auth_sessions table: hashed rotating refresh-token sessions per user

Revision ID: 0006_auth_sessions
Revises: 0005_email_tokens
Create Date: 2026-07-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_auth_sessions"
down_revision: str | None = "0005_email_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Rotation family: every rotation inserts a sibling sharing this id
        # and the family's single absolute expires_at.
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        # SHA-256 digest of the raw refresh token; the plaintext is never stored.
        sa.Column("token_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("token_hash", name="auth_sessions_token_hash_key"),
    )
    op.create_index("ix_sessions_user", "auth_sessions", ["user_id"])
    op.create_index("ix_sessions_family", "auth_sessions", ["family_id"])
    op.create_index("ix_sessions_expires_at", "auth_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("auth_sessions")  # drops its indexes with it
