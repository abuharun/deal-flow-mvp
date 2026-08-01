"""AnalysisJob ORM model mirrors Alembic revision 0010_analysis_jobs.

The model must be importable from app.models (so Base.metadata stays
complete for alembic autogenerate) and must encode the pilot contract: at
most one current job per startup (unique startup_id), and every bounded/safe
column carries the same CHECK-backed shape as the migration.
"""

from decimal import Decimal

from sqlalchemy import Integer, Numeric, Text

from app.models import AnalysisJob, Base
from app.models.analysis_job import (
    ALL_STATUSES,
    DEFAULT_MAX_ATTEMPTS,
    MAX_COST_ESTIMATE_USD,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RETRYING,
    STATUS_RUNNING,
    TERMINAL_STATUSES,
)

analysis_jobs = Base.metadata.tables["analysis_jobs"]


def test_analysis_job_is_importable_from_app_models():
    assert AnalysisJob.__tablename__ == "analysis_jobs"


def test_startup_id_is_a_unique_cascading_fk():
    startup_id = analysis_jobs.c.startup_id
    fk = next(iter(startup_id.foreign_keys))
    assert fk.column.table.name == "startups"
    assert fk.ondelete == "CASCADE"
    unique_constraints = {
        tuple(c.name for c in constraint.columns)
        for constraint in analysis_jobs.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("startup_id",) in unique_constraints, "at most one current job per startup"


def test_status_constants_match_the_canonical_five_values():
    assert ALL_STATUSES == (
        STATUS_QUEUED,
        STATUS_RUNNING,
        STATUS_RETRYING,
        STATUS_COMPLETED,
        STATUS_FAILED,
    )
    assert TERMINAL_STATUSES == {STATUS_COMPLETED, STATUS_FAILED}


def test_defaults_and_nullability():
    assert not analysis_jobs.c.input_revision.nullable
    assert not analysis_jobs.c.status.nullable
    assert STATUS_QUEUED in analysis_jobs.c.status.server_default.arg.text
    assert not analysis_jobs.c.attempts.nullable
    assert analysis_jobs.c.attempts.server_default.arg.text == "0"
    assert not analysis_jobs.c.max_attempts.nullable
    assert analysis_jobs.c.max_attempts.server_default.arg.text == str(DEFAULT_MAX_ATTEMPTS)
    for name in (
        "started_at",
        "heartbeat_at",
        "finished_at",
        "deadline_at",
        "next_attempt_at",
        "model",
        "prompt_version",
        "input_tokens",
        "output_tokens",
        "cost_estimate_usd",
        "last_error_code",
        "last_error_message_key",
    ):
        assert analysis_jobs.c[name].nullable, name


def test_numeric_and_integer_column_types():
    assert isinstance(analysis_jobs.c.input_revision.type, Integer)
    assert isinstance(analysis_jobs.c.attempts.type, Integer)
    assert isinstance(analysis_jobs.c.max_attempts.type, Integer)
    assert isinstance(analysis_jobs.c.input_tokens.type, Integer)
    assert isinstance(analysis_jobs.c.output_tokens.type, Integer)
    assert isinstance(analysis_jobs.c.cost_estimate_usd.type, Numeric)
    assert isinstance(analysis_jobs.c.model.type, Text)
    assert isinstance(analysis_jobs.c.last_error_code.type, Text)
    assert isinstance(analysis_jobs.c.last_error_message_key.type, Text)


def test_max_cost_estimate_constant_matches_the_db_check():
    assert MAX_COST_ESTIMATE_USD == Decimal("0.25")


def test_analysis_job_model_has_no_provider_or_secret_columns():
    # Defense in depth: this row must never carry raw provider payloads,
    # founder answers, deck bytes/URLs, or credentials.
    forbidden_substrings = (
        "secret",
        "token_value",
        "api_key",
        "content",
        "answer",
        "url",
        "hash",
        "raw",
    )
    for column_name in analysis_jobs.c.keys():
        lowered = column_name.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), column_name
