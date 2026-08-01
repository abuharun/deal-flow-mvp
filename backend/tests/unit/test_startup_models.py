"""Startup/Submission ORM models mirror Alembic revision 0007_startups.

The models must be importable from app.models (so Base.metadata stays complete
for alembic autogenerate) and must encode the ownership contract: founder_id
is indexed but NEVER unique, while submissions.startup_id IS unique (1:1).
"""

from sqlalchemy import BigInteger, Integer, Text

from app.models import Base, Startup, StartupStatus, Submission

startups = Base.metadata.tables["startups"]
submissions = Base.metadata.tables["submissions"]


def test_startup_status_members_match_the_pg_enum():
    assert [status.value for status in StartupStatus] == [
        "draft",
        "submitted",
        "analyzing",
        "report_ready",
        "vc_visible",
    ]


def test_founder_id_is_a_non_unique_indexed_fk_to_users():
    founder_id = startups.c.founder_id
    assert not founder_id.unique, "a founder owns MULTIPLE startups; never unique"
    fk = next(iter(founder_id.foreign_keys))
    assert fk.column.table.name == "users"
    assert fk.ondelete == "CASCADE"
    founder_indexes = [
        index for index in startups.indexes if [c.name for c in index.columns] == ["founder_id"]
    ]
    assert founder_indexes and not any(index.unique for index in founder_indexes)


def test_startup_columns_defaults_and_nullability():
    assert startups.c.status.server_default is not None
    assert startups.c.input_revision.server_default.arg.text == "1"
    assert isinstance(startups.c.input_revision.type, Integer)
    for name in ("name", "one_liner", "sector", "funding_stage", "city"):
        assert isinstance(startups.c[name].type, Text), name
        assert not startups.c[name].nullable, name
    for name in ("submitted_at", "vc_visible_at"):
        assert startups.c[name].nullable, name


def test_submission_startup_id_is_a_unique_cascading_fk():
    startup_id = submissions.c.startup_id
    fk = next(iter(startup_id.foreign_keys))
    assert fk.column.table.name == "startups"
    assert fk.ondelete == "CASCADE"
    unique_constraints = {
        tuple(c.name for c in constraint.columns)
        for constraint in submissions.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("startup_id",) in unique_constraints, "the questionnaire is strictly one per startup"


def test_submission_answer_columns_and_financials():
    for name in ("problem", "product", "market", "traction", "team", "ask"):
        column = submissions.c[name]
        assert isinstance(column.type, Text), name
        assert not column.nullable, name
        assert column.server_default is not None, name
    for name in ("revenue", "growth", "ask_amount", "dataroom_url"):
        assert submissions.c[name].nullable, name
    assert isinstance(submissions.c.ask_amount.type, BigInteger)


def test_startup_and_submission_are_linked_one_to_one():
    relationship = Startup.__mapper__.relationships["submission"]
    assert relationship.uselist is False
    assert relationship.mapper.class_ is Submission
