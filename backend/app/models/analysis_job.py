"""Durable per-startup AI analysis job queue/state.

Mirrors Alembic revision 0010_analysis_jobs; keep the two in sync.

Contract: at most one current analysis job per startup for this pilot
(UNIQUE startup_id). A job is tied to the exact input_revision of its
startup at trigger time — if the founder later edits their input or deck,
the startup's input_revision moves forward but this row's input_revision
never does, so any future report from this job is stale (see
`job.input_revision != startup.input_revision` in the status endpoint).
This module defines the row and its legal terminal shape only; no field
here is ever populated by calling a real provider in this slice.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_RETRYING = "retrying"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
ALL_STATUSES = (STATUS_QUEUED, STATUS_RUNNING, STATUS_RETRYING, STATUS_COMPLETED, STATUS_FAILED)
TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_FAILED})

DEFAULT_MAX_ATTEMPTS = 3
MIN_MAX_ATTEMPTS = 1
MAX_MAX_ATTEMPTS = 3
MAX_MODEL_LENGTH = 128
MAX_PROMPT_VERSION_LENGTH = 32
MAX_ERROR_CODE_LENGTH = 64
MAX_ERROR_MESSAGE_KEY_LENGTH = 128
MAX_COST_ESTIMATE_USD = Decimal("0.25")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        UniqueConstraint("startup_id", name="uq_analysis_jobs_startup_id"),
        CheckConstraint("input_revision >= 1", name="ck_analysis_jobs_input_revision_min"),
        CheckConstraint(
            "status IN ('queued', 'running', 'retrying', 'completed', 'failed')",
            name="ck_analysis_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_analysis_jobs_attempts_min"),
        CheckConstraint("max_attempts BETWEEN 1 AND 3", name="ck_analysis_jobs_max_attempts_range"),
        CheckConstraint(
            "(status = 'queued' AND started_at IS NULL) OR "
            "(status != 'queued' AND started_at IS NOT NULL)",
            name="ck_analysis_jobs_started_at_matches_status",
        ),
        CheckConstraint(
            "(status IN ('completed', 'failed') AND finished_at IS NOT NULL) OR "
            "(status NOT IN ('completed', 'failed') AND finished_at IS NULL)",
            name="ck_analysis_jobs_finished_at_matches_status",
        ),
        CheckConstraint(
            "model IS NULL OR char_length(model) BETWEEN 1 AND 128",
            name="ck_analysis_jobs_model_length",
        ),
        CheckConstraint(
            "prompt_version IS NULL OR char_length(prompt_version) BETWEEN 1 AND 32",
            name="ck_analysis_jobs_prompt_version_length",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_analysis_jobs_input_tokens_min",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_analysis_jobs_output_tokens_min",
        ),
        CheckConstraint(
            "cost_estimate_usd IS NULL OR (cost_estimate_usd >= 0 AND cost_estimate_usd <= 0.25)",
            name="ck_analysis_jobs_cost_estimate_range",
        ),
        CheckConstraint(
            r"last_error_code IS NULL OR last_error_code ~ '^[A-Z0-9_]{1,64}$'",
            name="ck_analysis_jobs_last_error_code_safe",
        ),
        CheckConstraint(
            "last_error_message_key IS NULL OR "
            r"last_error_message_key ~ '^[a-z][a-zA-Z0-9]*(\.[a-z][a-zA-Z0-9]*)+$'",
            name="ck_analysis_jobs_last_error_message_key_pattern",
        ),
        CheckConstraint(
            "last_error_message_key IS NULL OR char_length(last_error_message_key) <= 128",
            name="ck_analysis_jobs_last_error_message_key_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False
    )
    input_revision: Mapped[int] = mapped_column(Integer(), nullable=False)
    status: Mapped[str] = mapped_column(
        Text(), nullable=False, server_default=text(f"'{STATUS_QUEUED}'")
    )
    attempts: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("3"))
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model: Mapped[str | None] = mapped_column(Text())
    prompt_version: Mapped[str | None] = mapped_column(Text())
    input_tokens: Mapped[int | None] = mapped_column(Integer())
    output_tokens: Mapped[int | None] = mapped_column(Integer())
    cost_estimate_usd: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    last_error_code: Mapped[str | None] = mapped_column(Text())
    last_error_message_key: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
