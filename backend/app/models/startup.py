"""Founder-owned startups and their 1:1 questionnaire submissions.

Mirrors Alembic revision 0007_startups; keep the two in sync.

Ownership contract: a founder account owns and manages MULTIPLE startups, so
founder_id is indexed but NEVER unique. A startup stays editable until it
becomes VC-visible; material founder-input changes bump the monotonically
increasing input_revision (enforced >= 1 at the database level).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.models.user import pg_enum


class StartupStatus(enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ANALYZING = "analyzing"
    REPORT_READY = "report_ready"
    VC_VISIBLE = "vc_visible"


class Startup(Base):
    __tablename__ = "startups"
    __table_args__ = (
        Index("ix_startups_founder", "founder_id"),
        CheckConstraint("input_revision >= 1", name="ck_startups_input_revision_min"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    founder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text(), nullable=False)
    one_liner: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))
    sector: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))
    funding_stage: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))
    city: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))
    status: Mapped[StartupStatus] = mapped_column(
        pg_enum(StartupStatus, "startup_status"), nullable=False, server_default=text("'draft'")
    )
    input_revision: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("1"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vc_visible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    submission: Mapped["Submission"] = relationship(
        back_populates="startup", uselist=False, cascade="all, delete-orphan"
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        # One submission per startup — the questionnaire is strictly 1:1.
        UniqueConstraint("startup_id", name="uq_submissions_startup_id"),
        CheckConstraint(
            "ask_amount IS NULL OR ask_amount >= 0", name="ck_submissions_ask_amount_min"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("startups.id", ondelete="CASCADE"),
        nullable=False,
    )
    problem: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))
    product: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))
    market: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))
    traction: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))
    team: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))
    ask: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))
    revenue: Mapped[str | None] = mapped_column(Text())
    growth: Mapped[str | None] = mapped_column(Text())
    ask_amount: Mapped[int | None] = mapped_column(BigInteger())
    dataroom_url: Mapped[str | None] = mapped_column(Text())
    completed_steps: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, server_default=text("'{}'::text[]")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    startup: Mapped[Startup] = relationship(back_populates="submission")
