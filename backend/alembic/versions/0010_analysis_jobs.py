"""analysis_jobs: durable per-startup AI analysis job queue/state

Revision ID: 0010_analysis_jobs
Revises: 0009_payment_consent
Create Date: 2026-08-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_analysis_jobs"
down_revision: str | None = "0009_payment_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_RETRYING = "retrying"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
TERMINAL_STATUSES = (STATUS_COMPLETED, STATUS_FAILED)


def upgrade() -> None:
    op.create_table(
        "analysis_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # UNIQUE: at most one current analysis job per startup for the pilot.
        # A future explicit reanalysis migration may version jobs; this slice
        # never overwrites provenance of an existing row.
        sa.Column(
            "startup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("startups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The startup's input_revision at trigger time; a later founder edit
        # makes any report from this job stale without touching this value.
        sa.Column("input_revision", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text(f"'{STATUS_QUEUED}'")
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_estimate_usd", sa.Numeric(6, 4), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("last_error_message_key", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("startup_id", name="uq_analysis_jobs_startup_id"),
        sa.CheckConstraint("input_revision >= 1", name="ck_analysis_jobs_input_revision_min"),
        sa.CheckConstraint(
            f"status IN ('{STATUS_QUEUED}', '{STATUS_RUNNING}', '{STATUS_RETRYING}', "
            f"'{STATUS_COMPLETED}', '{STATUS_FAILED}')",
            name="ck_analysis_jobs_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_analysis_jobs_attempts_min"),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 3", name="ck_analysis_jobs_max_attempts_range"
        ),
        # Coherence: started_at is set once the job leaves 'queued' and never
        # before; finished_at is set iff the job reached a terminal status.
        sa.CheckConstraint(
            f"(status = '{STATUS_QUEUED}' AND started_at IS NULL) OR "
            f"(status != '{STATUS_QUEUED}' AND started_at IS NOT NULL)",
            name="ck_analysis_jobs_started_at_matches_status",
        ),
        sa.CheckConstraint(
            f"(status IN ('{STATUS_COMPLETED}', '{STATUS_FAILED}') AND finished_at IS NOT NULL) "
            f"OR (status NOT IN ('{STATUS_COMPLETED}', '{STATUS_FAILED}') "
            "AND finished_at IS NULL)",
            name="ck_analysis_jobs_finished_at_matches_status",
        ),
        sa.CheckConstraint(
            "model IS NULL OR char_length(model) BETWEEN 1 AND 128",
            name="ck_analysis_jobs_model_length",
        ),
        sa.CheckConstraint(
            "prompt_version IS NULL OR char_length(prompt_version) BETWEEN 1 AND 32",
            name="ck_analysis_jobs_prompt_version_length",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_analysis_jobs_input_tokens_min",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_analysis_jobs_output_tokens_min",
        ),
        sa.CheckConstraint(
            "cost_estimate_usd IS NULL OR (cost_estimate_usd >= 0 AND cost_estimate_usd <= 0.25)",
            name="ck_analysis_jobs_cost_estimate_range",
        ),
        # Bounded, safe (fixed-charset) fields only — never free-text/exception
        # bodies, so a failure code/key can never carry provider or SQL detail.
        sa.CheckConstraint(
            r"last_error_code IS NULL OR last_error_code ~ '^[A-Z0-9_]{1,64}$'",
            name="ck_analysis_jobs_last_error_code_safe",
        ),
        sa.CheckConstraint(
            "last_error_message_key IS NULL OR "
            r"last_error_message_key ~ '^[a-z][a-zA-Z0-9]*(\.[a-z][a-zA-Z0-9]*)+$'",
            name="ck_analysis_jobs_last_error_message_key_pattern",
        ),
        sa.CheckConstraint(
            "last_error_message_key IS NULL OR char_length(last_error_message_key) <= 128",
            name="ck_analysis_jobs_last_error_message_key_length",
        ),
    )


def downgrade() -> None:
    op.drop_table("analysis_jobs")
