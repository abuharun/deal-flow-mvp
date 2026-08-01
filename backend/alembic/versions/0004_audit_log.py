"""audit_log table: append-only trail enforced by a DB trigger

Revision ID: 0004_audit_log
Revises: 0003_invites
Create Date: 2026-07-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_audit_log"
down_revision: str | None = "0003_invites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False: creation/drop is done explicitly (checkfirst) below so the
# upgrade/downgrade sequence stays safe to re-run after a partial failure.
AUDIT_ACTOR_TYPE = postgresql.ENUM(
    "user", "cli", "worker", "system", name="audit_actor_type", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    AUDIT_ACTOR_TYPE.create(bind, checkfirst=True)
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("actor_type", AUDIT_ACTOR_TYPE, nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Sanitized by audit_service before insert: never secrets/PDF bytes/full answers.
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ip", postgresql.INET(), nullable=True),
    )
    op.create_index("ix_audit_at", "audit_log", ["at"])
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id"])
    # The trigger is the authoritative append-only guarantee: REVOKE cannot
    # bind the table owner, which is exactly who the app connects as today.
    op.execute(
        """
        CREATE FUNCTION audit_log_block_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % rejected', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    # Statement-level so even zero-row UPDATE/DELETE statements are rejected.
    op.execute(
        "CREATE TRIGGER trg_audit_log_append_only "
        "BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_block_mutation()"
    )
    # Defense in depth for future non-owner application roles.
    op.execute("REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC")


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("audit_log")  # drops its indexes and trigger with it
    op.execute("DROP FUNCTION IF EXISTS audit_log_block_mutation()")
    AUDIT_ACTOR_TYPE.drop(bind, checkfirst=True)
    # citext stays: shared extension owned by no single revision (see 0002).
