"""analysis_reports + report_sources: immutable, source-cited AI research reports

Revision ID: 0011_analysis_reports
Revises: 0010_analysis_jobs
Create Date: 2026-08-01

One report per startup and per analysis job (both UNIQUE), storing the exact
input_revision/model/prompt_version/schema_version the report was generated
from -- a report never changes once written; a later founder edit only makes
it STALE (report.input_revision != startups.input_revision), never mutated.
Normalized citations live in report_sources, one row per cited source, keyed
by a per-report ordinal that report JSONB citation_ids reference.

Immutability is enforced the same way as audit_log (0004): REVOKE alone
cannot bind the table owner (the role the app connects as), so a BEFORE
UPDATE OR DELETE FOR EACH STATEMENT trigger is the authoritative guarantee,
shared by both tables via one trigger function. Unlike audit_log, a DELETE is
let through when it is a cascaded effect of hard-deleting the owning startup
(pg_trigger_depth() > 1) -- direct UPDATE/DELETE against these tables is
always rejected.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011_analysis_reports"
down_revision: str | None = "0010_analysis_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_VERSION_REPORT_V1 = "report.v1"
LANGUAGE_EN = "en"
MAX_MODEL_LENGTH = 128
MAX_PROMPT_VERSION_LENGTH = 32
MAX_TITLE_LENGTH = 300
MAX_SNIPPET_LENGTH = 1000
MAX_URL_LENGTH = 2048
SOURCE_QUALITIES = ("primary", "reputable_media", "industry", "blog", "unknown")
CONFIDENCE_LEVELS = ("high", "medium", "low")


def upgrade() -> None:
    op.create_table(
        "analysis_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # UNIQUE: exactly one immutable report per startup for this pilot.
        sa.Column(
            "startup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("startups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # UNIQUE: exactly one report per completed analysis job.
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The startup's input_revision at the moment the underlying job was
        # triggered -- never updated; staleness is computed by comparing this
        # to the startup's CURRENT input_revision at read time.
        sa.Column("input_revision", sa.Integer(), nullable=False),
        sa.Column(
            "schema_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text(f"'{SCHEMA_VERSION_REPORT_V1}'"),
        ),
        sa.Column(
            "language", sa.Text(), nullable=False, server_default=sa.text(f"'{LANGUAGE_EN}'")
        ),
        # Cited narrative/claims/sections/checklist -- validated against the
        # report.v1 Pydantic schema before insert; never chain-of-thought,
        # hidden prompts, or raw provider response bodies.
        sa.Column("report", postgresql.JSONB(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("partial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("evidence_count", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("startup_id", name="uq_analysis_reports_startup_id"),
        sa.UniqueConstraint("job_id", name="uq_analysis_reports_job_id"),
        sa.CheckConstraint("input_revision >= 1", name="ck_analysis_reports_input_revision_min"),
        sa.CheckConstraint(
            f"schema_version = '{SCHEMA_VERSION_REPORT_V1}'",
            name="ck_analysis_reports_schema_version",
        ),
        sa.CheckConstraint(f"language = '{LANGUAGE_EN}'", name="ck_analysis_reports_language"),
        sa.CheckConstraint(
            f"char_length(model) BETWEEN 1 AND {MAX_MODEL_LENGTH}",
            name="ck_analysis_reports_model_length",
        ),
        sa.CheckConstraint(
            f"char_length(prompt_version) BETWEEN 1 AND {MAX_PROMPT_VERSION_LENGTH}",
            name="ck_analysis_reports_prompt_version_length",
        ),
        sa.CheckConstraint(
            "evidence_count IS NULL OR evidence_count >= 0",
            name="ck_analysis_reports_evidence_count_min",
        ),
    )

    op.create_table(
        "report_sources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 1-based position within its report -- report.json citation_ids
        # reference this ordinal, never a source's opaque UUID.
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published_date", sa.Date(), nullable=True),
        sa.Column("accessed_date", sa.Date(), nullable=False),
        sa.Column("source_quality", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.UniqueConstraint("report_id", "ordinal", name="uq_report_sources_report_ordinal"),
        sa.CheckConstraint("ordinal >= 1", name="ck_report_sources_ordinal_min"),
        sa.CheckConstraint(
            f"char_length(url) BETWEEN 1 AND {MAX_URL_LENGTH} AND "
            r"url ~ '^https?://[^\s\x00-\x1f\x7f]+$'",
            name="ck_report_sources_url_safe",
        ),
        sa.CheckConstraint(
            f"char_length(title) BETWEEN 1 AND {MAX_TITLE_LENGTH}",
            name="ck_report_sources_title_length",
        ),
        sa.CheckConstraint(
            "source_quality IN (" + ", ".join(f"'{value}'" for value in SOURCE_QUALITIES) + ")",
            name="ck_report_sources_source_quality",
        ),
        sa.CheckConstraint(
            "confidence IN (" + ", ".join(f"'{value}'" for value in CONFIDENCE_LEVELS) + ")",
            name="ck_report_sources_confidence",
        ),
        sa.CheckConstraint(
            f"snippet IS NULL OR char_length(snippet) <= {MAX_SNIPPET_LENGTH}",
            name="ck_report_sources_snippet_length",
        ),
    )

    # DELETE is allowed only when it is a cascaded effect of hard-deleting the
    # owning startup (startup_id/report_id ON DELETE CASCADE), never a direct
    # application/admin statement -- pg_trigger_depth() is 1 for a top-level
    # DELETE against this table and >1 when Postgres reached it by cascading
    # from a FK ON DELETE CASCADE action higher up. UPDATE has no legitimate
    # cascade case and is always rejected.
    op.execute(
        """
        CREATE FUNCTION analysis_report_block_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
                RETURN NULL;
            END IF;
            RAISE EXCEPTION 'analysis reports are immutable: % rejected on %', TG_OP, TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_analysis_reports_immutable "
        "BEFORE UPDATE OR DELETE ON analysis_reports "
        "FOR EACH STATEMENT EXECUTE FUNCTION analysis_report_block_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_report_sources_immutable "
        "BEFORE UPDATE OR DELETE ON report_sources "
        "FOR EACH STATEMENT EXECUTE FUNCTION analysis_report_block_mutation()"
    )
    # Defense in depth for future non-owner application roles.
    op.execute("REVOKE UPDATE, DELETE ON analysis_reports FROM PUBLIC")
    op.execute("REVOKE UPDATE, DELETE ON report_sources FROM PUBLIC")


def downgrade() -> None:
    op.drop_table("report_sources")  # drops its indexes and trigger with it
    op.drop_table("analysis_reports")
    op.execute("DROP FUNCTION IF EXISTS analysis_report_block_mutation()")
