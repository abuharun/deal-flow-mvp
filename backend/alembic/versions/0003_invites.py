"""invites table: hashed one-time invite tokens for VC-owner activation

Revision ID: 0003_invites
Revises: 0002_users
Create Date: 2026-07-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_invites"
down_revision: str | None = "0002_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        # SHA-256 digest of the raw token; the plaintext is never stored.
        sa.Column("token_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("token_hash", name="invites_token_hash_key"),
    )
    # Non-unique: re-inviting the same email issues a fresh token.
    op.create_index("ix_invites_email", "invites", ["email"])
    op.create_index("ix_invites_expires_at", "invites", ["expires_at"])


def downgrade() -> None:
    op.drop_table("invites")  # drops its indexes with it
    # citext stays: shared extension owned by no single revision (see 0002).
