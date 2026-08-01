"""Unit tests for the User model's declared intent (Task B1, slice 2)."""

from app.models import Base
from app.models.user import UiLocale, User, UserRole


def test_enum_values_match_db_labels():
    assert [r.value for r in UserRole] == ["founder", "vc"]
    assert [x.value for x in UiLocale] == ["uz", "ru"]


def test_users_table_is_registered_on_base_metadata():
    # alembic/env.py autogenerate only sees tables known to Base.metadata.
    assert "users" in Base.metadata.tables
    assert User.__table__ is Base.metadata.tables["users"]


def test_declared_defaults_and_nullability_mirror_the_migration():
    t = User.__table__
    assert "gen_random_uuid" in str(t.c.id.server_default.arg)
    assert "uz" in str(t.c.locale.server_default.arg)
    assert t.c.email.unique
    for name in ("email", "password_hash", "full_name", "role", "locale"):
        assert not t.c[name].nullable, name
    for name in ("email_verified_at", "deleted_at", "purge_after"):
        assert t.c[name].nullable, name
    assert t.c.created_at.server_default is not None
    assert t.c.updated_at.server_default is not None
