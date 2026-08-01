"""Immutable, source-cited AI research reports.

Mirrors Alembic revision 0011_analysis_reports; keep the two in sync.

Contract: at most one report per startup and per analysis job (both UNIQUE).
A report's input_revision is fixed at the value the underlying job carried
when it was created -- it is never updated afterward. Staleness is a
READ-time comparison (report.input_revision != startup.input_revision), not
a column. Rows in both tables here are protected from direct UPDATE/DELETE
by a DB trigger (see the migration) that still permits a DELETE cascaded
from hard-deleting the owning startup; this module defines no update/delete
method for either model on purpose.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

SCHEMA_VERSION_REPORT_V1 = "report.v1"
LANGUAGE_EN = "en"
MAX_MODEL_LENGTH = 128
MAX_PROMPT_VERSION_LENGTH = 32
MAX_TITLE_LENGTH = 300
MAX_SNIPPET_LENGTH = 1000
MAX_URL_LENGTH = 2048
SOURCE_QUALITIES = ("primary", "reputable_media", "industry", "blog", "unknown")
CONFIDENCE_LEVELS = ("high", "medium", "low")


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"
    __table_args__ = (
        UniqueConstraint("startup_id", name="uq_analysis_reports_startup_id"),
        UniqueConstraint("job_id", name="uq_analysis_reports_job_id"),
        CheckConstraint("input_revision >= 1", name="ck_analysis_reports_input_revision_min"),
        CheckConstraint(
            f"schema_version = '{SCHEMA_VERSION_REPORT_V1}'",
            name="ck_analysis_reports_schema_version",
        ),
        CheckConstraint(f"language = '{LANGUAGE_EN}'", name="ck_analysis_reports_language"),
        CheckConstraint(
            f"char_length(model) BETWEEN 1 AND {MAX_MODEL_LENGTH}",
            name="ck_analysis_reports_model_length",
        ),
        CheckConstraint(
            f"char_length(prompt_version) BETWEEN 1 AND {MAX_PROMPT_VERSION_LENGTH}",
            name="ck_analysis_reports_prompt_version_length",
        ),
        CheckConstraint(
            "evidence_count IS NULL OR evidence_count >= 0",
            name="ck_analysis_reports_evidence_count_min",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False
    )
    input_revision: Mapped[int] = mapped_column(Integer(), nullable=False)
    schema_version: Mapped[str] = mapped_column(
        Text(), nullable=False, server_default=text(f"'{SCHEMA_VERSION_REPORT_V1}'")
    )
    language: Mapped[str] = mapped_column(
        Text(), nullable=False, server_default=text(f"'{LANGUAGE_EN}'")
    )
    report: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    model: Mapped[str] = mapped_column(Text(), nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text(), nullable=False)
    partial: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default=text("false"))
    evidence_count: Mapped[int | None] = mapped_column(Integer())
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReportSource(Base):
    __tablename__ = "report_sources"
    __table_args__ = (
        UniqueConstraint("report_id", "ordinal", name="uq_report_sources_report_ordinal"),
        CheckConstraint("ordinal >= 1", name="ck_report_sources_ordinal_min"),
        CheckConstraint(
            f"char_length(url) BETWEEN 1 AND {MAX_URL_LENGTH} AND "
            r"url ~ '^https?://[^\s\x00-\x1f\x7f]+$'",
            name="ck_report_sources_url_safe",
        ),
        CheckConstraint(
            f"char_length(title) BETWEEN 1 AND {MAX_TITLE_LENGTH}",
            name="ck_report_sources_title_length",
        ),
        CheckConstraint(
            "source_quality IN (" + ", ".join(f"'{v}'" for v in SOURCE_QUALITIES) + ")",
            name="ck_report_sources_source_quality",
        ),
        CheckConstraint(
            "confidence IN (" + ", ".join(f"'{v}'" for v in CONFIDENCE_LEVELS) + ")",
            name="ck_report_sources_confidence",
        ),
        CheckConstraint(
            f"snippet IS NULL OR char_length(snippet) <= {MAX_SNIPPET_LENGTH}",
            name="ck_report_sources_snippet_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_reports.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer(), nullable=False)
    url: Mapped[str] = mapped_column(Text(), nullable=False)
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    published_date: Mapped[date | None] = mapped_column(Date())
    accessed_date: Mapped[date] = mapped_column(Date(), nullable=False)
    source_quality: Mapped[str] = mapped_column(Text(), nullable=False)
    confidence: Mapped[str] = mapped_column(Text(), nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text())
