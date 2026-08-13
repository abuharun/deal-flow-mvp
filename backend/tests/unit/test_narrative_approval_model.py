"""The approval ORM model mirrors Alembic revision 0013_narrative_approvals.

The model must be importable from app.models (so Base.metadata stays complete
for alembic autogenerate) and must encode the contract that makes an approval
trustworthy: one per startup, no narrative text of its own, and a whole-tuple
foreign key so the version it names cannot be another startup's, a different
version number, or a different report than the one it claims.
"""

from sqlalchemy import DateTime, Integer

from app.models import Base, NarrativeApproval

approvals = Base.metadata.tables["narrative_approvals"]
versions = Base.metadata.tables["narrative_versions"]


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


def test_columns_types_and_nullability():
    expected_columns = {
        "id",
        "startup_id",
        "narrative_version_id",
        "version",
        "report_id",
        "approved_by",
        "approved_at",
    }
    assert set(approvals.c.keys()) == expected_columns
    assert isinstance(approvals.c.version.type, Integer)
    assert isinstance(approvals.c.approved_at.type, DateTime)
    assert approvals.c.approved_at.type.timezone is True
    for name in expected_columns:
        assert not approvals.c[name].nullable, name


def test_the_approval_stores_no_narrative_text():
    # The approved narrative IS the immutable version row this names; a copy
    # of the text here could drift from what the history says.
    for forbidden in ("content", "narrative", "text"):
        assert forbidden not in approvals.c, forbidden


def test_a_startup_can_be_approved_at_most_once():
    assert ("startup_id",) in _unique_column_tuples(approvals)


def test_the_approved_version_is_referenced_as_a_whole_identity():
    composite = [
        constraint
        for constraint in approvals.foreign_key_constraints
        if len(constraint.columns) > 1
    ]
    assert composite, "the approval must reference the version's whole identity as one unit"
    constraint = composite[0]
    assert {column.name for column in constraint.columns} == {
        "narrative_version_id",
        "startup_id",
        "version",
        "report_id",
    }
    assert constraint.referred_table.name == "narrative_versions"
    assert constraint.ondelete == "CASCADE"


def test_the_version_history_exposes_that_identity_as_a_unique_key():
    # PostgreSQL only accepts an FK target covering exactly the referenced
    # columns, so the history must carry the matching UNIQUE constraint.
    assert ("id", "startup_id", "version", "report_id") in _unique_column_tuples(versions)


def test_the_approving_founder_and_startup_cascade_on_hard_delete():
    # startup_id carries two references -- its own to startups and its share
    # of the composite identity key -- so each is looked up by target.
    for column, target in (
        (approvals.c.startup_id, "startups"),
        (approvals.c.approved_by, "users"),
    ):
        matching = [fk for fk in column.foreign_keys if fk.column.table.name == target]
        assert matching, f"{column.name} must reference {target}"
        assert matching[0].ondelete == "CASCADE", column.name


def test_the_version_number_is_bounded_at_the_database_level():
    assert _check_names(approvals) == {"ck_narrative_approvals_version_min"}


def test_the_model_exposes_no_update_delete_or_revoke_helper():
    # Immutability is enforced by the DB trigger; the mapped class must not
    # offer a convenience method that looks like a supported mutation --
    # there is no un-approve in this slice.
    for attribute in ("update", "delete", "revoke", "unapprove"):
        assert not hasattr(NarrativeApproval, attribute), attribute


def test_the_approval_records_no_recipient_or_delivery_state():
    # Approval freezes the narrative and makes the startup VC-visible. Which
    # investors see it, and when it is sent, is deliberately future work.
    for forbidden in ("sent_at", "recipient_id", "audience", "delivered_at", "vc_id"):
        assert forbidden not in approvals.c, forbidden
