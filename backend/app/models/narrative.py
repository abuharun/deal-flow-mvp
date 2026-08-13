"""Founder-editable pitch narrative with append-only version history.

Mirrors Alembic revision 0012_narratives; keep the two in sync.

Contract: ONE free-text narrative per startup, written in whatever language
the founder chooses -- nothing here is keyed by UI locale. `NarrativeVersion`
is append-only history (UNIQUE (startup_id, version)) protected from direct
UPDATE/DELETE by a DB trigger (see the migration) that still permits a
DELETE cascaded from hard-deleting an owning row; this module defines no
update/delete method for it on purpose. `StartupNarrative` is the mutable
one-per-startup pointer at the current version and stores no text of its
own, so "current" and "history" can never disagree about what the narrative
says.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

SOURCE_REPORT_SEED = "report_seed"
SOURCE_FOUNDER_EDIT = "founder_edit"
NARRATIVE_SOURCES = (SOURCE_REPORT_SEED, SOURCE_FOUNDER_EDIT)

MAX_NARRATIVE_CONTENT_LENGTH = 20_000

# Everything in C0 except tab and newline, plus DEL. Carriage returns are
# excluded on purpose: the request schema normalizes CRLF/CR to LF before
# any write, so a stored \r would mean something bypassed it.
CONTENT_CONTROL_CHAR_CLASS = r"[\x01-\x08\x0b-\x1f\x7f]"
CONTENT_NOT_BLANK = r"AND btrim(content, E' \t\n\r') <> ''"


class NarrativeVersion(Base):
    __tablename__ = "narrative_versions"
    __table_args__ = (
        UniqueConstraint("startup_id", "version", name="uq_narrative_versions_startup_version"),
        # FK target for an approval's whole-identity reference (see
        # app.models.narrative_approval and revision 0013). Redundant for
        # uniqueness -- id is the primary key -- and required by PostgreSQL,
        # which only accepts a UNIQUE constraint covering exactly the
        # referenced columns.
        UniqueConstraint(
            "id", "startup_id", "version", "report_id", name="uq_narrative_versions_identity"
        ),
        CheckConstraint("version >= 1", name="ck_narrative_versions_version_min"),
        CheckConstraint("input_revision >= 1", name="ck_narrative_versions_input_revision_min"),
        CheckConstraint(
            f"char_length(content) BETWEEN 1 AND {MAX_NARRATIVE_CONTENT_LENGTH} "
            + CONTENT_NOT_BLANK,
            name="ck_narrative_versions_content_bounds",
        ),
        CheckConstraint(
            f"content !~ '{CONTENT_CONTROL_CHAR_CLASS}'",
            name="ck_narrative_versions_content_no_control_chars",
        ),
        CheckConstraint(
            "source IN (" + ", ".join(f"'{value}'" for value in NARRATIVE_SOURCES) + ")",
            name="ck_narrative_versions_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer(), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    source: Mapped[str] = mapped_column(Text(), nullable=False)
    # The immutable report whose pitch_narrative_draft seeded this lineage.
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_reports.id", ondelete="CASCADE"), nullable=False
    )
    # The startup's input_revision when this version was written -- NOT the
    # report's; the two answer different questions (see the migration).
    input_revision: Mapped[int] = mapped_column(Integer(), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StartupNarrative(Base):
    __tablename__ = "startup_narratives"
    __table_args__ = (
        UniqueConstraint("startup_id", name="uq_startup_narratives_startup_id"),
        # The pointer must name a version of THIS startup: (startup_id,
        # current_version) is checked as one unit against the history's
        # UNIQUE key, so cross-startup pointers are impossible.
        ForeignKeyConstraint(
            ["startup_id", "current_version"],
            ["narrative_versions.startup_id", "narrative_versions.version"],
            name="fk_startup_narratives_current_version",
            ondelete="CASCADE",
        ),
        CheckConstraint("current_version >= 1", name="ck_startup_narratives_current_version_min"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False
    )
    current_version: Mapped[int] = mapped_column(Integer(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
