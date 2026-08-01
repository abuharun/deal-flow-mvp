"""email_tokens table: hashed one-time verification/reset tokens per user

Revision ID: 0005_email_tokens
Revises: 0004_audit_log
Create Date: 2026-07-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_email_tokens"
down_revision: str | None = "0004_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False: creation/drop is done explicitly (checkfirst) below so the
# upgrade/downgrade sequence stays safe to re-run after a partial failure.
EMAIL_TOKEN_PURPOSE = postgresql.ENUM(
    "verify", "reset", name="email_token_purpose", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    EMAIL_TOKEN_PURPOSE.create(bind, checkfirst=True)
    op.create_table(
        "email_tokens",
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
        sa.Column("purpose", EMAIL_TOKEN_PURPOSE, nullable=False),
        # SHA-256 digest of the raw token; the plaintext is never stored.
        sa.Column("token_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("token_hash", name="email_tokens_token_hash_key"),
    )
    op.create_index("ix_email_tokens_user_purpose", "email_tokens", ["user_id", "purpose"])
    op.create_index("ix_email_tokens_expires_at", "email_tokens", ["expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("email_tokens")  # drops its indexes with it
    EMAIL_TOKEN_PURPOSE.drop(bind, checkfirst=True)
