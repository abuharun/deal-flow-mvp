"""payment_consent: per-startup demo payment + versioned AI/privacy consent

Revision ID: 0009_payment_consent
Revises: 0008_pitch_decks
Create Date: 2026-08-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_payment_consent"
down_revision: str | None = "0008_pitch_decks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAYMENT_MODE_DEMO = "demo"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_FAILED = "failed"
PAYMENT_LABEL_DEMO = "demo_payment"
CONSENT_KIND_AI_PRIVACY = "ai_privacy"
MAX_TEXT_VERSION_LENGTH = 32


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # UNIQUE: exactly one current pilot payment row per startup.
        sa.Column(
            "startup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("startups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mode", sa.Text(), nullable=False, server_default=sa.text(f"'{PAYMENT_MODE_DEMO}'")
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "label", sa.Text(), nullable=False, server_default=sa.text(f"'{PAYMENT_LABEL_DEMO}'")
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("startup_id", name="uq_payments_startup_id"),
        # Defence in depth: this is an honest demo/stub, never a real
        # gateway — the DB itself refuses any value implying otherwise.
        sa.CheckConstraint(f"mode = '{PAYMENT_MODE_DEMO}'", name="ck_payments_mode"),
        sa.CheckConstraint(
            f"status IN ('{PAYMENT_STATUS_PAID}', '{PAYMENT_STATUS_FAILED}')",
            name="ck_payments_status",
        ),
        sa.CheckConstraint(f"label = '{PAYMENT_LABEL_DEMO}'", name="ck_payments_label"),
        sa.CheckConstraint(
            f"(status = '{PAYMENT_STATUS_PAID}' AND paid_at IS NOT NULL) OR "
            f"(status = '{PAYMENT_STATUS_FAILED}' AND paid_at IS NULL)",
            name="ck_payments_paid_at_matches_status",
        ),
    )

    op.create_table(
        "consents",
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
        sa.Column(
            "founder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("text_version", sa.Text(), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Same startup/kind/version can never be granted twice; a different
        # text_version is a distinct row, so consent history is preserved.
        sa.UniqueConstraint(
            "startup_id", "kind", "text_version", name="uq_consents_startup_kind_version"
        ),
        sa.CheckConstraint(f"kind = '{CONSENT_KIND_AI_PRIVACY}'", name="ck_consents_kind"),
        sa.CheckConstraint(
            f"char_length(text_version) BETWEEN 1 AND {MAX_TEXT_VERSION_LENGTH}",
            name="ck_consents_text_version_length",
        ),
    )
    op.create_index("ix_consents_startup", "consents", ["startup_id"])


def downgrade() -> None:
    op.drop_index("ix_consents_startup", table_name="consents")
    op.drop_table("consents")
    op.drop_table("payments")
