"""write_audit against a real AsyncSession (Task B2, slice 2).

Contracts under test:
- flushes but never commits — the caller owns the transaction boundary;
- sensitive metadata keys are recursively redacted before anything reaches
  the database, without mutating the caller's dict;
- actions are dot-namespaced and bounded, entity types bounded.
"""

import copy
import json
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from app.db import build_engine, build_sessionmaker
from app.logging_setup import REDACTED
from app.models import AuditActorType
from app.services.audit_service import (
    MAX_ACTION_LENGTH,
    MAX_ENTITY_TYPE_LENGTH,
    write_audit,
)

FROZEN_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def session(engine):
    # No commit anywhere in these tests: rollback on exit keeps the DB clean.
    async with build_sessionmaker(engine)() as session:
        yield session
        await session.rollback()


async def _fetch_rows(conn_or_session, entity_id: uuid.UUID) -> list[dict]:
    result = await conn_or_session.execute(
        sa.text(
            "SELECT at, actor_type, actor_id, action, entity_type, entity_id, "
            "CAST(metadata AS text) AS metadata, host(ip) AS ip "
            "FROM audit_log WHERE entity_id = :entity_id"
        ),
        {"entity_id": entity_id},
    )
    return [dict(row) for row in result.mappings()]


async def test_write_audit_persists_full_row(session):
    entity_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    await write_audit(
        session,
        actor_type=AuditActorType.CLI,
        actor_id=actor_id,
        action="cli.create_invite",
        entity_type="invite",
        entity_id=entity_id,
        metadata={"email": "invitee@example.com"},
        ip="203.0.113.7",
    )

    (row,) = await _fetch_rows(session, entity_id)
    assert row["actor_type"] == "cli"
    assert row["actor_id"] == actor_id
    assert row["action"] == "cli.create_invite"
    assert row["entity_type"] == "invite"
    assert row["entity_id"] == entity_id
    assert json.loads(row["metadata"]) == {"email": "invitee@example.com"}
    assert row["ip"] == "203.0.113.7"
    assert row["at"].tzinfo is not None
    assert abs((row["at"] - datetime.now(UTC)).total_seconds()) < 60


async def test_optional_fields_default_to_null_and_empty_metadata(session):
    entity_id = uuid.uuid4()
    await write_audit(
        session,
        actor_type=AuditActorType.SYSTEM,
        action="retention.purge",
        entity_type="user",
        entity_id=entity_id,
    )

    (row,) = await _fetch_rows(session, entity_id)
    assert row["actor_id"] is None
    assert row["ip"] is None
    assert json.loads(row["metadata"]) == {}


async def test_injected_at_is_deterministic(session):
    entity_id = uuid.uuid4()
    await write_audit(
        session,
        actor_type=AuditActorType.WORKER,
        action="analysis.completed",
        entity_type="analysis_job",
        entity_id=entity_id,
        at=FROZEN_NOW,
    )
    (row,) = await _fetch_rows(session, entity_id)
    assert row["at"] == FROZEN_NOW


async def test_sensitive_metadata_is_recursively_redacted_before_reaching_db(session):
    entity_id = uuid.uuid4()
    secrets = [
        "raw-password-hunter2",
        "raw-token-abc123",
        "raw-jwt-secret",
        "Bearer raw-header",
        "session=raw-cookie",
        "raw-founder-content",
        "raw-model-answer",
        "raw-model-prompt",
    ]
    metadata = {
        "email": "safe@example.com",
        "password": secrets[0],
        "nested": {
            "invite_token": secrets[1],
            "jwt_secret": secrets[2],
            "deep": [{"Authorization": secrets[3]}, {"Cookie": secrets[4]}],
        },
        # "answers" itself matches the policy (substring "answer"): whole value masked.
        "answers": ["whole-list-masked"],
        "fields": [{"content": secrets[5], "answer": secrets[6], "prompt": secrets[7]}],
    }

    await write_audit(
        session,
        actor_type=AuditActorType.CLI,
        action="cli.create_vc_owner",
        entity_type="user",
        entity_id=entity_id,
        metadata=metadata,
    )

    (row,) = await _fetch_rows(session, entity_id)
    stored = json.loads(row["metadata"])
    assert stored["email"] == "safe@example.com", "safe keys must survive redaction"
    assert stored["password"] == REDACTED
    assert stored["nested"]["invite_token"] == REDACTED
    assert stored["nested"]["jwt_secret"] == REDACTED
    assert stored["nested"]["deep"] == [{"Authorization": REDACTED}, {"Cookie": REDACTED}]
    assert stored["answers"] == REDACTED
    assert stored["fields"] == [{"content": REDACTED, "answer": REDACTED, "prompt": REDACTED}]
    for secret in secrets:
        assert secret not in row["metadata"], "no sensitive value may reach the database"


async def test_redaction_never_mutates_caller_metadata(session):
    metadata = {"password": "hunter2", "nested": {"token": "abc", "list": [{"secret": "s"}]}}
    snapshot = copy.deepcopy(metadata)
    await write_audit(
        session,
        actor_type=AuditActorType.CLI,
        action="cli.create_vc_owner",
        entity_type="user",
        entity_id=uuid.uuid4(),
        metadata=metadata,
    )
    assert metadata == snapshot, "the caller's dict must not be mutated"


@pytest.mark.parametrize(
    "action",
    [
        "nodot",
        "",
        ".leading",
        "trailing.",
        "two..dots",
        "x." + "a" * 200,  # over MAX_ACTION_LENGTH
    ],
)
async def test_invalid_actions_are_rejected_without_touching_the_db(session, action):
    assert len("x." + "a" * 200) > MAX_ACTION_LENGTH
    with pytest.raises(ValueError):
        await write_audit(
            session,
            actor_type=AuditActorType.CLI,
            action=action,
            entity_type="invite",
        )
    assert not session.new, "validation must fail before anything is staged"


@pytest.mark.parametrize("entity_type", ["", "e" * 200])
async def test_invalid_entity_types_are_rejected(session, entity_type):
    assert len("e" * 200) > MAX_ENTITY_TYPE_LENGTH
    with pytest.raises(ValueError):
        await write_audit(
            session,
            actor_type=AuditActorType.CLI,
            action="cli.create_invite",
            entity_type=entity_type,
        )
    assert not session.new


async def test_write_audit_never_commits_rollback_discards_the_row(engine, session):
    entity_id = uuid.uuid4()
    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        action="auth.login",
        entity_type="user",
        entity_id=entity_id,
    )
    # Visible inside the caller's transaction (the row was flushed) ...
    assert len(await _fetch_rows(session, entity_id)) == 1
    # ... invisible outside it before commit ...
    async with engine.connect() as conn:
        assert await _fetch_rows(conn, entity_id) == []
    # ... and gone after the caller rolls back.
    await session.rollback()
    assert await _fetch_rows(session, entity_id) == []
    async with engine.connect() as conn:
        assert await _fetch_rows(conn, entity_id) == []
