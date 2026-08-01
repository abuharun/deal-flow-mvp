"""Payment/Consent ORM models mirror Alembic revision 0009_payment_consent.

The models must be importable from app.models (so Base.metadata stays
complete for alembic autogenerate) and must encode the ownership/isolation
contract: both tables key off startup_id (never a bare founder-level grant),
payments.startup_id is unique (one current payment per startup), and
consents' uniqueness is scoped to (startup_id, kind, text_version) so a new
text_version is always a fresh, history-preserving row.
"""

from sqlalchemy import Text

from app.models import Base, Consent, Payment
from app.models.consent import CONSENT_KIND_AI_PRIVACY, CURRENT_AI_PRIVACY_VERSION
from app.models.payment import (
    PAYMENT_LABEL_DEMO,
    PAYMENT_MODE_DEMO,
    PAYMENT_STATUS_FAILED,
    PAYMENT_STATUS_PAID,
)

payments = Base.metadata.tables["payments"]
consents = Base.metadata.tables["consents"]


def test_payment_startup_id_is_a_unique_cascading_fk():
    startup_id = payments.c.startup_id
    fk = next(iter(startup_id.foreign_keys))
    assert fk.column.table.name == "startups"
    assert fk.ondelete == "CASCADE"
    unique_constraints = {
        tuple(c.name for c in constraint.columns)
        for constraint in payments.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("startup_id",) in unique_constraints, "one current payment row per startup"


def test_payment_columns_defaults_and_nullability():
    assert isinstance(payments.c.mode.type, Text)
    assert not payments.c.mode.nullable
    assert PAYMENT_MODE_DEMO in payments.c.mode.server_default.arg.text
    assert not payments.c.status.nullable
    assert not payments.c.label.nullable
    assert PAYMENT_LABEL_DEMO in payments.c.label.server_default.arg.text
    assert payments.c.paid_at.nullable
    assert not payments.c.created_at.nullable
    assert not payments.c.updated_at.nullable


def test_payment_status_constants_are_paid_and_failed():
    assert PAYMENT_STATUS_PAID == "paid"
    assert PAYMENT_STATUS_FAILED == "failed"


def test_payment_model_has_no_provider_or_secret_columns():
    # Defense in depth against ever wiring a real gateway into this table.
    forbidden_substrings = ("token", "secret", "provider", "card", "gateway", "session_id")
    for column_name in payments.c.keys():
        lowered = column_name.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), column_name


def test_consent_startup_and_founder_are_cascading_fks():
    startup_fk = next(iter(consents.c.startup_id.foreign_keys))
    assert startup_fk.column.table.name == "startups"
    assert startup_fk.ondelete == "CASCADE"
    founder_fk = next(iter(consents.c.founder_id.foreign_keys))
    assert founder_fk.column.table.name == "users"
    assert founder_fk.ondelete == "CASCADE"


def test_consent_uniqueness_is_scoped_to_startup_kind_and_version():
    unique_constraints = {
        tuple(c.name for c in constraint.columns)
        for constraint in consents.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("startup_id", "kind", "text_version") in unique_constraints


def test_consent_columns_defaults_and_nullability():
    for name in ("startup_id", "founder_id", "kind", "text_version", "granted_at"):
        assert not consents.c[name].nullable, name
    assert consents.c.granted_at.server_default is not None


def test_consent_kind_and_current_version_constants():
    assert CONSENT_KIND_AI_PRIVACY == "ai_privacy"
    assert CURRENT_AI_PRIVACY_VERSION == "ai-privacy.v1"


def test_payment_and_consent_are_importable_from_app_models():
    assert Payment.__tablename__ == "payments"
    assert Consent.__tablename__ == "consents"
