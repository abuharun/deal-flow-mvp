"""The founder's explicit approval that freezes one narrative version.

Mirrors Alembic revision 0013_narrative_approvals; keep the two in sync.

Contract: at most ONE approval per startup (UNIQUE startup_id). It stores no
narrative text of its own -- only which immutable `NarrativeVersion` was
approved, by whom, and when -- so the approved text is always the version row
it names and the two can never disagree.

Identity is checked as one unit: (narrative_version_id, startup_id, version,
report_id) is a composite FK into narrative_versions' matching UNIQUE key, so
an approval can never name another startup's version, claim a version number
its row does not have, or credit the wrong report.

Rows here are protected from direct UPDATE/DELETE by a DB trigger (see the
migration) that still permits a DELETE cascaded from hard-deleting an owning
row; this module defines no update/delete method on purpose. The same
migration freezes the narrative itself once an approval exists: no new
version may be inserted for that startup and its current pointer cannot move.

What an approval is NOT: a delivery. It records the freeze and the transition
to VC-visible only -- which investors may see it, and when it is sent, is
deliberately left to future work.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class NarrativeApproval(Base):
    __tablename__ = "narrative_approvals"
    __table_args__ = (
        UniqueConstraint("startup_id", name="uq_narrative_approvals_startup_id"),
        CheckConstraint("version >= 1", name="ck_narrative_approvals_version_min"),
        # The whole identity of the approved version, checked as one unit.
        ForeignKeyConstraint(
            ["narrative_version_id", "startup_id", "version", "report_id"],
            [
                "narrative_versions.id",
                "narrative_versions.startup_id",
                "narrative_versions.version",
                "narrative_versions.report_id",
            ],
            name="fk_narrative_approvals_version_identity",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False
    )
    narrative_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Denormalized from the version row: the composite FK above makes
    # disagreement impossible, and "which version was approved" then needs no
    # join in reads or audit metadata.
    version: Mapped[int] = mapped_column(Integer(), nullable=False)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approved_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
