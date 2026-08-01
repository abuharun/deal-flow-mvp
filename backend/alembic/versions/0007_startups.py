"""startups + submissions: founder-owned startup records with 1:1 questionnaires

Revision ID: 0007_startups
Revises: 0006_auth_sessions
Create Date: 2026-08-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_startups"
down_revision: str | None = "0006_auth_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False: creation/drop is done explicitly (checkfirst) below so the
# upgrade/downgrade sequence stays safe to re-run after a partial failure.
STARTUP_STATUS = postgresql.ENUM(
    "draft",
    "submitted",
    "analyzing",
    "report_ready",
    "vc_visible",
    name="startup_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    STARTUP_STATUS.create(bind, checkfirst=True)
    op.create_table(
        "startups",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # NEVER unique: one founder account owns and manages MULTIPLE startups.
        sa.Column(
            "founder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("one_liner", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("sector", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("funding_stage", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("city", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("status", STARTUP_STATUS, nullable=False, server_default=sa.text("'draft'")),
        # Monotonically increasing count of material founder-input revisions;
        # starts at 1 and never goes below it.
        sa.Column("input_revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vc_visible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("input_revision >= 1", name="ck_startups_input_revision_min"),
    )
    op.create_index("ix_startups_founder", "startups", ["founder_id"])

    op.create_table(
        "submissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "startup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("startups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("problem", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("product", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("market", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("traction", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("team", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("ask", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("revenue", sa.Text(), nullable=True),
        sa.Column("growth", sa.Text(), nullable=True),
        sa.Column("ask_amount", sa.BigInteger(), nullable=True),
        sa.Column("dataroom_url", sa.Text(), nullable=True),
        sa.Column(
            "completed_steps",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # One submission per startup — the questionnaire is strictly 1:1.
        sa.UniqueConstraint("startup_id", name="uq_submissions_startup_id"),
        sa.CheckConstraint(
            "ask_amount IS NULL OR ask_amount >= 0", name="ck_submissions_ask_amount_min"
        ),
    )


def downgrade() -> None:
    op.drop_table("submissions")
    op.drop_table("startups")  # drops ix_startups_founder with it
    STARTUP_STATUS.drop(op.get_bind(), checkfirst=True)
