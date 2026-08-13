"""narrative_versions + startup_narratives: founder-editable narrative, immutable history

Revision ID: 0012_narratives
Revises: 0011_analysis_reports
Create Date: 2026-08-13

Product decision for the MVP: a startup has exactly ONE free-text pitch
narrative. The founder chooses the language it is written in -- the UI
locale (UZ/RU) never splits the text, so there is deliberately no language
column and no (startup_id, locale) key here.

The feature is split across two tables so that "editable" and "immutable"
are separate physical things:

- narrative_versions is append-only history. One row per saved version,
  numbered monotonically per startup (UNIQUE (startup_id, version)), each
  carrying the provenance it was written against: report_id (the immutable
  report whose pitch_narrative_draft seeded the lineage) and input_revision
  (the startup's founder-input revision at the moment of the save). Those
  two answer different questions and are both kept: the report's own
  input_revision says what the AI analyzed, this one says what the founder's
  answers looked like when they wrote this text.
- startup_narratives is the mutable CURRENT pointer, one row per startup
  (UNIQUE startup_id). It stores no text at all -- only which version is
  current -- so the current narrative IS an immutable version row and the
  two can never drift apart. A composite FK into
  narrative_versions (startup_id, version) means the pointer can never name
  a version that does not exist, or one belonging to a different startup.

Immutability is enforced the same way as audit_log (0004) and
analysis_reports (0011): REVOKE alone cannot bind the table owner (the role
the app connects as), so a BEFORE UPDATE OR DELETE FOR EACH STATEMENT
trigger is the authoritative guarantee. As in 0011, a DELETE is let through
when it is a cascaded effect of hard-deleting an owning row
(pg_trigger_depth() > 1) so account/startup deletion stays possible; direct
UPDATE/DELETE against narrative_versions is always rejected. The pointer
table is intentionally NOT protected: moving it forward is how a save takes
effect.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012_narratives"
down_revision: str | None = "0011_analysis_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_REPORT_SEED = "report_seed"
SOURCE_FOUNDER_EDIT = "founder_edit"
NARRATIVE_SOURCES = (SOURCE_REPORT_SEED, SOURCE_FOUNDER_EDIT)

MAX_NARRATIVE_CONTENT_LENGTH = 20_000

# Everything in C0 except tab (\x09) and newline (\x0a), plus DEL. Carriage
# returns are excluded on purpose: the request schema normalizes CRLF/CR to
# LF before any write, so a stored \r would mean something bypassed it.
CONTENT_CONTROL_CHAR_CLASS = r"[\x01-\x08\x0b-\x1f\x7f]"

# Whitespace-only text is not a narrative: btrim's default only strips
# spaces, so the trimmed set is spelled out.
CONTENT_NOT_BLANK = r"AND btrim(content, E' \t\n\r') <> ''"


def upgrade() -> None:
    op.create_table(
        "narrative_versions",
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
        # 1-based and monotonic per startup; allocated under the startup's
        # row lock, with the UNIQUE constraint below as the backstop.
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        # The immutable report this narrative lineage was seeded from.
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The startup's input_revision when this version was written.
        sa.Column("input_revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("startup_id", "version", name="uq_narrative_versions_startup_version"),
        sa.CheckConstraint("version >= 1", name="ck_narrative_versions_version_min"),
        sa.CheckConstraint("input_revision >= 1", name="ck_narrative_versions_input_revision_min"),
        sa.CheckConstraint(
            f"char_length(content) BETWEEN 1 AND {MAX_NARRATIVE_CONTENT_LENGTH} "
            + CONTENT_NOT_BLANK,
            name="ck_narrative_versions_content_bounds",
        ),
        sa.CheckConstraint(
            f"content !~ '{CONTENT_CONTROL_CHAR_CLASS}'",
            name="ck_narrative_versions_content_no_control_chars",
        ),
        sa.CheckConstraint(
            "source IN (" + ", ".join(f"'{value}'" for value in NARRATIVE_SOURCES) + ")",
            name="ck_narrative_versions_source",
        ),
    )

    op.create_table(
        "startup_narratives",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # UNIQUE: exactly one current narrative per startup.
        sa.Column(
            "startup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("startups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_version", sa.Integer(), nullable=False),
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
        sa.UniqueConstraint("startup_id", name="uq_startup_narratives_startup_id"),
        # The pointer must name a version of THIS startup -- (startup_id,
        # current_version) is checked as one unit against the history's
        # UNIQUE key, so cross-startup pointers are impossible.
        sa.ForeignKeyConstraint(
            ["startup_id", "current_version"],
            ["narrative_versions.startup_id", "narrative_versions.version"],
            name="fk_startup_narratives_current_version",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "current_version >= 1", name="ck_startup_narratives_current_version_min"
        ),
    )

    # DELETE is allowed only as a cascaded effect of hard-deleting an owning
    # row (startup/report/user), never a direct application or admin
    # statement -- pg_trigger_depth() is 1 for a top-level DELETE against
    # this table and > 1 when Postgres reached it by cascading. UPDATE has no
    # legitimate cascade case here and is always rejected.
    op.execute(
        """
        CREATE FUNCTION narrative_version_block_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
                RETURN NULL;
            END IF;
            RAISE EXCEPTION 'narrative versions are immutable: % rejected on %',
                TG_OP, TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_narrative_versions_immutable "
        "BEFORE UPDATE OR DELETE ON narrative_versions "
        "FOR EACH STATEMENT EXECUTE FUNCTION narrative_version_block_mutation()"
    )
    # Defense in depth for future non-owner application roles.
    op.execute("REVOKE UPDATE, DELETE ON narrative_versions FROM PUBLIC")


def downgrade() -> None:
    op.drop_table("startup_narratives")  # references narrative_versions
    op.drop_table("narrative_versions")  # drops its trigger with it
    op.execute("DROP FUNCTION IF EXISTS narrative_version_block_mutation()")
