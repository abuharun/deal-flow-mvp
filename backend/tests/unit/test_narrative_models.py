"""Narrative ORM models mirror Alembic revision 0012_narratives.

Both models must be importable from app.models (so Base.metadata stays
complete for alembic autogenerate) and must encode the two halves of the
contract: narrative_versions is append-only history keyed (startup_id,
version), and startup_narratives is the single mutable pointer per startup
that names one of those versions -- and stores no narrative text itself.
"""

from sqlalchemy import Integer, Text

from app.models import Base, NarrativeVersion, StartupNarrative
from app.models.narrative import (
    MAX_NARRATIVE_CONTENT_LENGTH,
    NARRATIVE_SOURCES,
    SOURCE_FOUNDER_EDIT,
    SOURCE_REPORT_SEED,
)

versions = Base.metadata.tables["narrative_versions"]
current = Base.metadata.tables["startup_narratives"]


def _unique_column_tuples(table) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }


def _check_names(table) -> set[str]:
    return {
        constraint.name
        for constraint in table.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }


def test_narrative_sources_are_exactly_the_two_canonical_values():
    assert NARRATIVE_SOURCES == (SOURCE_REPORT_SEED, SOURCE_FOUNDER_EDIT)
    assert SOURCE_REPORT_SEED == "report_seed"
    assert SOURCE_FOUNDER_EDIT == "founder_edit"


def test_version_columns_types_and_nullability():
    expected_columns = {
        "id",
        "startup_id",
        "version",
        "content",
        "source",
        "report_id",
        "input_revision",
        "created_by",
        "created_at",
    }
    assert set(versions.c.keys()) == expected_columns
    assert isinstance(versions.c.content.type, Text)
    assert isinstance(versions.c.version.type, Integer)
    assert isinstance(versions.c.input_revision.type, Integer)
    for name in expected_columns:
        assert not versions.c[name].nullable, name


def test_version_is_unique_per_startup_so_history_can_never_fork():
    assert ("startup_id", "version") in _unique_column_tuples(versions)


def test_version_foreign_keys_cascade_from_startup_report_and_author():
    for column, target in (
        (versions.c.startup_id, "startups"),
        (versions.c.report_id, "analysis_reports"),
        (versions.c.created_by, "users"),
    ):
        fk = next(iter(column.foreign_keys))
        assert fk.column.table.name == target
        assert fk.ondelete == "CASCADE", column.name


def test_version_checks_bound_content_source_and_provenance():
    assert _check_names(versions) == {
        "ck_narrative_versions_version_min",
        "ck_narrative_versions_input_revision_min",
        "ck_narrative_versions_content_bounds",
        "ck_narrative_versions_content_no_control_chars",
        "ck_narrative_versions_source",
    }


def test_the_model_exposes_no_update_or_delete_helper():
    # Immutability is enforced by the DB trigger; the mapped class must not
    # offer a convenience method that looks like a supported mutation.
    for attribute in ("update", "delete", "edit", "rewrite"):
        assert not hasattr(NarrativeVersion, attribute), attribute


def test_current_pointer_columns_and_absence_of_content():
    assert set(current.c.keys()) == {
        "id",
        "startup_id",
        "current_version",
        "created_at",
        "updated_at",
    }
    assert "content" not in current.c, "the pointer must never duplicate narrative text"
    assert isinstance(current.c.current_version.type, Integer)
    assert current.c.updated_at.onupdate is not None


def test_only_one_current_narrative_per_startup():
    assert ("startup_id",) in _unique_column_tuples(current)


def test_current_pointer_has_a_composite_fk_into_the_version_history():
    composite = [
        constraint
        for constraint in current.foreign_key_constraints
        if {column.name for column in constraint.columns} == {"startup_id", "current_version"}
    ]
    assert composite, "the pointer must reference (startup_id, version) as one unit"
    constraint = composite[0]
    assert constraint.referred_table.name == "narrative_versions"
    assert constraint.ondelete == "CASCADE"


def test_current_version_is_bounded_at_the_database_level():
    assert "ck_startup_narratives_current_version_min" in _check_names(current)


def test_content_length_limit_leaves_room_for_a_real_pitch_narrative():
    # The seed comes from report.v1's 3000-char pitch_narrative_draft; the
    # founder-editable narrative is deliberately roomier than that.
    assert MAX_NARRATIVE_CONTENT_LENGTH == 20_000
    assert StartupNarrative.__tablename__ == "startup_narratives"
    assert NarrativeVersion.__tablename__ == "narrative_versions"
