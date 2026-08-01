"""users table + user_role/ui_locale enums + citext extension

Revision ID: 0002_users
Revises: 0001_baseline
Create Date: 2026-07-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_users"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False: creation/drop is done explicitly (checkfirst) below so the
# upgrade/downgrade sequence stays safe to re-run after a partial failure.
USER_ROLE = postgresql.ENUM("founder", "vc", name="user_role", create_type=False)
UI_LOCALE = postgresql.ENUM("uz", "ru", name="ui_locale", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    # citext makes email uniqueness case-insensitive at the type level.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    USER_ROLE.create(bind, checkfirst=True)
    UI_LOCALE.create(bind, checkfirst=True)
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("role", USER_ROLE, nullable=False),
        sa.Column("locale", UI_LOCALE, nullable=False, server_default=sa.text("'uz'")),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("email", name="users_email_key"),
    )
    op.create_index(
        "ix_users_purge",
        "users",
        ["purge_after"],
        postgresql_where=sa.text("purge_after IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("users")  # drops its indexes with it
    UI_LOCALE.drop(bind, checkfirst=True)
    USER_ROLE.drop(bind, checkfirst=True)
    # citext stays: extensions are shared database state, not owned by this revision.
