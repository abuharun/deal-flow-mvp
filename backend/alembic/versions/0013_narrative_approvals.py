"""narrative_approvals: the founder's explicit freeze of one narrative version

Revision ID: 0013_narrative_approvals
Revises: 0012_narratives
Create Date: 2026-08-13

Product decision: going VC-visible is an explicit act by the founder, not a
side effect of finishing an analysis. Approval names ONE immutable narrative
version -- the one the founder is looking at -- and from that moment the
startup is locked: that exact text is what an investor will eventually read.

What this migration deliberately does NOT model: which investors may see it,
when it is sent, and to whom. The audience policy stays future work; an
approval here is a freeze plus visibility, never a delivery or a recipient
assignment.

narrative_approvals stores no narrative text at all -- only which version was
approved, by whom, and when. The approved text is therefore always the
`narrative_versions` row it names, so an approval and the history can never
disagree about what was approved.

Four database-level guarantees, because the application must not be the only
thing between an approved pitch and a silent rewrite:

1. Identity. The approval carries (narrative_version_id, startup_id, version,
   report_id) and a composite FK checks all four as ONE unit against
   narrative_versions. A row claiming to be "version 2 of startup X, from
   report R" while pointing at some other version's id cannot exist. That
   composite target needs a matching UNIQUE constraint on narrative_versions,
   which this revision adds (redundant for uniqueness -- id is already the
   primary key -- and required by PostgreSQL as an FK target).
2. Currency. An AFTER INSERT trigger requires the approved version to be the
   startup's CURRENT narrative version at insert time: approving is defined
   as freezing what the founder is looking at, never resurrecting an older
   revision. AFTER (not BEFORE) so ordinary CHECK/FK violations still surface
   as themselves rather than as this trigger's error.
3. Immutability. Direct UPDATE/DELETE on an approval is rejected by a trigger
   -- REVOKE cannot bind the table owner, which is the role the app connects
   as -- following audit_log (0004), analysis_reports (0011), and
   narrative_versions (0012). A DELETE cascaded from hard-deleting an owning
   row (pg_trigger_depth() > 1) is still allowed so account/startup deletion
   remains possible.
4. Freeze. Once an approval exists for a startup, no new narrative version
   may be inserted for it and its current pointer may not move. The
   application refuses these with the canonical STARTUP_LOCKED long before
   they reach here; this is the guarantee behind that promise, and it is
   scoped per startup so every other founder's narrative stays editable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_narrative_approvals"
down_revision: str | None = "0012_narratives"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # FK target for the composite identity check below. `id` alone is already
    # unique (primary key); PostgreSQL requires a UNIQUE constraint covering
    # exactly the referenced columns, so this spells the whole tuple out.
    op.create_unique_constraint(
        "uq_narrative_versions_identity",
        "narrative_versions",
        ["id", "startup_id", "version", "report_id"],
    )

    op.create_table(
        "narrative_approvals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # UNIQUE: a startup is approved at most once. Re-approving the same
        # version is idempotent in the service and must never append a row.
        sa.Column(
            "startup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("startups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("narrative_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Denormalized from the version row on purpose: the composite FK below
        # makes disagreement impossible, and reads/audits that only need "which
        # version was approved" never have to join.
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("startup_id", name="uq_narrative_approvals_startup_id"),
        sa.CheckConstraint("version >= 1", name="ck_narrative_approvals_version_min"),
        # The whole identity as one unit: this startup's version, that exact
        # row, seeded from that exact report.
        sa.ForeignKeyConstraint(
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

    # Guarantee 2 -- an approval may only freeze the CURRENT version.
    op.execute(
        """
        CREATE FUNCTION narrative_approval_current_version() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM startup_narratives
                WHERE startup_id = NEW.startup_id AND current_version = NEW.version
            ) THEN
                RAISE EXCEPTION
                    'narrative approval must name the startup''s current narrative version';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_narrative_approvals_current_version "
        "AFTER INSERT ON narrative_approvals "
        "FOR EACH ROW EXECUTE FUNCTION narrative_approval_current_version()"
    )

    # Guarantee 3 -- approvals are immutable (see 0011/0012 for the pattern).
    op.execute(
        """
        CREATE FUNCTION narrative_approval_block_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
                RETURN NULL;
            END IF;
            RAISE EXCEPTION 'narrative approvals are immutable: % rejected on %',
                TG_OP, TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_narrative_approvals_immutable "
        "BEFORE UPDATE OR DELETE ON narrative_approvals "
        "FOR EACH STATEMENT EXECUTE FUNCTION narrative_approval_block_mutation()"
    )
    op.execute("REVOKE UPDATE, DELETE ON narrative_approvals FROM PUBLIC")

    # Guarantee 4 -- an approved startup's narrative is frozen: no new version,
    # and the current pointer stays where the approval found it. NEW.startup_id
    # exists in both events, so one function serves both tables.
    op.execute(
        """
        CREATE FUNCTION narrative_block_after_approval() RETURNS trigger AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM narrative_approvals WHERE startup_id = NEW.startup_id) THEN
                RAISE EXCEPTION
                    'narrative is approved and frozen: % rejected on %', TG_OP, TG_TABLE_NAME;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_narrative_versions_frozen_after_approval "
        "BEFORE INSERT ON narrative_versions "
        "FOR EACH ROW EXECUTE FUNCTION narrative_block_after_approval()"
    )
    op.execute(
        "CREATE TRIGGER trg_startup_narratives_frozen_after_approval "
        "BEFORE UPDATE ON startup_narratives "
        "FOR EACH ROW EXECUTE FUNCTION narrative_block_after_approval()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_startup_narratives_frozen_after_approval ON startup_narratives"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_narrative_versions_frozen_after_approval ON narrative_versions"
    )
    op.execute("DROP FUNCTION IF EXISTS narrative_block_after_approval()")
    op.drop_table("narrative_approvals")  # drops its own triggers with it
    op.execute("DROP FUNCTION IF EXISTS narrative_approval_current_version()")
    op.execute("DROP FUNCTION IF EXISTS narrative_approval_block_mutation()")
    op.drop_constraint("uq_narrative_versions_identity", "narrative_versions", type_="unique")
