"""baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-29

"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Baseline: establishes revision tracking only; no schema objects yet.
    pass


def downgrade() -> None:
    pass
