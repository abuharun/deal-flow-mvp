"""One demo/pilot payment row per startup — an honest simulation, never real.

Mirrors Alembic revision 0009_payment_consent; keep the two in sync.

Contract: `mode` is permanently 'demo' — there is no real payment gateway
behind this table, so nothing here (nor any response built from it) may ever
imply an actual charge occurred. The founder explicitly picks a simulated
outcome; `status` records exactly that choice. A successful ('paid') payment
never regresses to 'failed' — see payment_service for the transition rules
enforced at the application layer, and the paid_at/status CHECK below for the
matching DB-level invariant.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

PAYMENT_MODE_DEMO = "demo"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_FAILED = "failed"
PAYMENT_LABEL_DEMO = "demo_payment"


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        # One current pilot payment row per startup.
        UniqueConstraint("startup_id", name="uq_payments_startup_id"),
        CheckConstraint(f"mode = '{PAYMENT_MODE_DEMO}'", name="ck_payments_mode"),
        CheckConstraint(
            f"status IN ('{PAYMENT_STATUS_PAID}', '{PAYMENT_STATUS_FAILED}')",
            name="ck_payments_status",
        ),
        CheckConstraint(f"label = '{PAYMENT_LABEL_DEMO}'", name="ck_payments_label"),
        CheckConstraint(
            f"(status = '{PAYMENT_STATUS_PAID}' AND paid_at IS NOT NULL) OR "
            f"(status = '{PAYMENT_STATUS_FAILED}' AND paid_at IS NULL)",
            name="ck_payments_paid_at_matches_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(
        Text(), nullable=False, server_default=text(f"'{PAYMENT_MODE_DEMO}'")
    )
    status: Mapped[str] = mapped_column(Text(), nullable=False)
    label: Mapped[str] = mapped_column(
        Text(), nullable=False, server_default=text(f"'{PAYMENT_LABEL_DEMO}'")
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
