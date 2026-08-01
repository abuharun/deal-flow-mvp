"""create/rotate/revoke refresh sessions against a real AsyncSession (Task B4, slice A).

Contract under test:
- The service flushes but never commits — the caller owns the transaction
  boundary (the concurrency tests commit deliberately, as a real caller would).
- The database holds only SHA-256 digests; the raw token exists once, in the
  returned frozen grant, and never in reprs.
- A family shares one absolute expiry fixed at creation; rotation never
  extends it.
- Reuse of a rotated token atomically revokes the whole family (security
  first): under concurrent rotation of the same token exactly one caller wins
  ROTATED, the other sees REUSE, and the winner's child is left unusable.
- Outcome precedence: UNKNOWN, then REVOKED, then REUSE, then EXPIRED — reuse
  detection outranks expiry, and an expired-but-active token is reported
  EXPIRED without mutating any row.
"""

import asyncio
import dataclasses
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from app.db import build_engine, build_sessionmaker
from app.services.session_service import (
    REFRESH_SESSION_TTL,
    USER_AGENT_MAX_LENGTH,
    RotateOutcome,
    create_session,
    revoke_all_user_sessions,
    revoke_family_by_token,
    revoke_session_family,
    rotate_session,
)

FROZEN_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
LATER = FROZEN_NOW + timedelta(days=1)
EVEN_LATER = FROZEN_NOW + timedelta(days=2)
AFTER_EXPIRY = FROZEN_NOW + timedelta(days=30, seconds=1)


def frozen_clock() -> datetime:
    return FROZEN_NOW


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


async def _create_user(session) -> uuid.UUID:
    result = await session.execute(
        sa.text(
            "INSERT INTO users (email, password_hash, full_name, role) "
            "VALUES (:email, 'x', 'Session Owner', 'founder') RETURNING id"
        ),
        {"email": f"session-owner-{uuid.uuid4().hex}@example.com"},
    )
    return result.scalar_one()


async def _fetch_rows(conn_or_session, user_id: uuid.UUID) -> list[dict]:
    result = await conn_or_session.execute(
        sa.text(
            "SELECT id, user_id, family_id, token_hash, expires_at, rotated_at, "
            "revoked_at, user_agent, created_at "
            "FROM auth_sessions WHERE user_id = :user_id ORDER BY created_at, id"
        ),
        {"user_id": str(user_id)},
    )
    return [dict(row) for row in result.mappings()]


class TestCreateSession:
    async def test_stores_only_sha256_hash_and_absolute_30_day_expiry(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)

        (row,) = await _fetch_rows(session, user_id)
        assert row["token_hash"] == hashlib.sha256(grant.token.encode("ascii")).digest()
        for value in row.values():
            assert value != grant.token, "plaintext must never be stored"
        assert row["expires_at"] == FROZEN_NOW + timedelta(days=30)
        assert REFRESH_SESSION_TTL == timedelta(days=30)
        assert row["rotated_at"] is None
        assert row["revoked_at"] is None
        assert grant.auth_session.expires_at == FROZEN_NOW + timedelta(days=30)
        assert grant.auth_session.family_id == row["family_id"]

    async def test_grant_is_frozen_and_repr_never_leaks_the_raw_token(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        with pytest.raises(dataclasses.FrozenInstanceError):
            grant.token = "tampered"
        assert grant.token not in repr(grant)
        assert grant.token not in repr(grant.auth_session)

    async def test_injected_token_and_family_factories_are_used(self, session):
        user_id = await _create_user(session)
        family_id = uuid.uuid4()
        grant = await create_session(
            session,
            user_id=user_id,
            clock=frozen_clock,
            token_factory=lambda: "fixed-token",
            family_factory=lambda: family_id,
        )
        assert grant.token == "fixed-token"
        (row,) = await _fetch_rows(session, user_id)
        assert row["token_hash"] == hashlib.sha256(b"fixed-token").digest()
        assert row["family_id"] == family_id

    async def test_each_session_gets_its_own_token_and_family(self, session):
        user_id = await _create_user(session)
        first = await create_session(session, user_id=user_id, clock=frozen_clock)
        second = await create_session(session, user_id=user_id, clock=frozen_clock)
        assert first.token != second.token
        rows = await _fetch_rows(session, user_id)
        assert len({row["token_hash"] for row in rows}) == 2
        assert len({row["family_id"] for row in rows}) == 2

    async def test_user_agent_is_stored_and_truncated_safely(self, session):
        user_id = await _create_user(session)
        await create_session(
            session, user_id=user_id, clock=frozen_clock, user_agent="Mozilla/5.0 test"
        )
        await create_session(session, user_id=user_id, clock=frozen_clock, user_agent="x" * 10_000)
        await create_session(session, user_id=user_id, clock=frozen_clock, user_agent=None)
        agents = [row["user_agent"] for row in await _fetch_rows(session, user_id)]
        assert "Mozilla/5.0 test" in agents
        assert "x" * USER_AGENT_MAX_LENGTH in agents
        assert not any(a is not None and len(a) > USER_AGENT_MAX_LENGTH for a in agents)
        assert None in agents

    async def test_service_never_commits_rollback_discards_the_session(self, engine, session):
        user_id = await _create_user(session)
        await create_session(session, user_id=user_id, clock=frozen_clock)
        # Visible inside the caller's transaction (the row was flushed) ...
        assert len(await _fetch_rows(session, user_id)) == 1
        # ... invisible outside it before commit ...
        async with engine.connect() as conn:
            assert await _fetch_rows(conn, user_id) == []
        # ... and gone after the caller rolls back.
        await session.rollback()
        async with engine.connect() as conn:
            assert await _fetch_rows(conn, user_id) == []


class TestRotateSession:
    async def test_active_token_rotates_same_family_same_absolute_expiry(self, session):
        user_id = await _create_user(session)
        grant = await create_session(
            session, user_id=user_id, clock=frozen_clock, user_agent="rotating client"
        )
        result = await rotate_session(session, token=grant.token, clock=lambda: LATER)

        assert result.outcome is RotateOutcome.ROTATED
        assert result.grant is not None
        assert result.grant.token != grant.token

        # Both rows share created_at (now() is transaction-start time), so
        # identify them by token hash rather than by insertion order.
        rows = {row["token_hash"]: row for row in await _fetch_rows(session, user_id)}
        assert len(rows) == 2
        old = rows[hashlib.sha256(grant.token.encode("ascii")).digest()]
        new = rows[hashlib.sha256(result.grant.token.encode("ascii")).digest()]
        assert old["rotated_at"] == LATER
        assert old["revoked_at"] is None
        assert new["rotated_at"] is None
        assert new["revoked_at"] is None
        assert new["family_id"] == old["family_id"]
        assert new["expires_at"] == old["expires_at"] == FROZEN_NOW + timedelta(days=30), (
            "rotation must never extend the family's absolute expiry"
        )
        assert new["token_hash"] == hashlib.sha256(result.grant.token.encode("ascii")).digest()
        assert new["user_agent"] == "rotating client", "child keeps the family's user agent"

    async def test_rotation_result_never_leaks_raw_tokens(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        result = await rotate_session(session, token=grant.token, clock=lambda: LATER)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.outcome = RotateOutcome.UNKNOWN
        assert result.grant.token not in repr(result)
        assert grant.token not in repr(result)

    async def test_unknown_token_reports_unknown(self, session):
        result = await rotate_session(session, token="never-issued-token", clock=frozen_clock)
        assert result.outcome is RotateOutcome.UNKNOWN
        assert result.grant is None

    async def test_malformed_token_reports_unknown_without_raising(self, session):
        for malformed in ("", " ", "not base64 !!", "с-кириллицей", "a" * 10_000, "\x00\n"):
            result = await rotate_session(session, token=malformed, clock=frozen_clock)
            assert result.outcome is RotateOutcome.UNKNOWN, repr(malformed)

    async def test_expired_active_token_reports_expired_and_mutates_nothing(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        result = await rotate_session(session, token=grant.token, clock=lambda: AFTER_EXPIRY)
        assert result.outcome is RotateOutcome.EXPIRED
        assert result.grant is None
        (row,) = await _fetch_rows(session, user_id)
        assert row["rotated_at"] is None
        assert row["revoked_at"] is None

    async def test_exactly_at_expiry_is_expired(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        result = await rotate_session(
            session, token=grant.token, clock=lambda: FROZEN_NOW + timedelta(days=30)
        )
        assert result.outcome is RotateOutcome.EXPIRED

    async def test_revoked_token_reports_revoked(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        await revoke_session_family(
            session, family_id=grant.auth_session.family_id, clock=lambda: LATER
        )
        result = await rotate_session(session, token=grant.token, clock=lambda: EVEN_LATER)
        assert result.outcome is RotateOutcome.REVOKED
        assert result.grant is None

    async def test_reuse_of_rotated_token_revokes_the_entire_family(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        first = await rotate_session(session, token=grant.token, clock=lambda: LATER)
        assert first.outcome is RotateOutcome.ROTATED

        reuse = await rotate_session(session, token=grant.token, clock=lambda: EVEN_LATER)
        assert reuse.outcome is RotateOutcome.REUSE
        assert reuse.grant is None

        rows = await _fetch_rows(session, user_id)
        assert len(rows) == 2
        assert all(row["revoked_at"] == EVEN_LATER for row in rows), (
            "reuse must atomically revoke every row in the family"
        )
        # The child issued by the legitimate rotation is now unusable.
        child = await rotate_session(session, token=first.grant.token, clock=lambda: EVEN_LATER)
        assert child.outcome is RotateOutcome.REVOKED

    async def test_reuse_detection_outranks_expiry(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        await rotate_session(session, token=grant.token, clock=lambda: LATER)
        result = await rotate_session(session, token=grant.token, clock=lambda: AFTER_EXPIRY)
        assert result.outcome is RotateOutcome.REUSE
        rows = await _fetch_rows(session, user_id)
        assert all(row["revoked_at"] == AFTER_EXPIRY for row in rows)

    async def test_reuse_revocation_is_scoped_to_the_one_family(self, session):
        user_id = await _create_user(session)
        other_user_id = await _create_user(session)
        victim = await create_session(session, user_id=user_id, clock=frozen_clock)
        bystander = await create_session(session, user_id=user_id, clock=frozen_clock)
        other = await create_session(session, user_id=other_user_id, clock=frozen_clock)

        await rotate_session(session, token=victim.token, clock=lambda: LATER)
        reuse = await rotate_session(session, token=victim.token, clock=lambda: EVEN_LATER)
        assert reuse.outcome is RotateOutcome.REUSE

        by_family = {}
        for row in await _fetch_rows(session, user_id) + await _fetch_rows(session, other_user_id):
            by_family.setdefault(row["family_id"], []).append(row)
        assert all(r["revoked_at"] is not None for r in by_family[victim.auth_session.family_id])
        assert all(r["revoked_at"] is None for r in by_family[bystander.auth_session.family_id])
        assert all(r["revoked_at"] is None for r in by_family[other.auth_session.family_id])

    async def test_revoked_outranks_reuse_after_family_revocation(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        first = await rotate_session(session, token=grant.token, clock=lambda: LATER)
        assert first.outcome is RotateOutcome.ROTATED
        await revoke_session_family(
            session, family_id=grant.auth_session.family_id, clock=lambda: LATER
        )
        # The old token is both rotated and revoked; revocation answers first.
        result = await rotate_session(session, token=grant.token, clock=lambda: EVEN_LATER)
        assert result.outcome is RotateOutcome.REVOKED


class TestConcurrentRotation:
    async def test_concurrent_same_token_one_rotated_one_reuse_child_unusable(
        self, engine, db_at_head
    ):
        """Two callers race the same token: SELECT FOR UPDATE serializes them.

        The winner rotates and commits; the loser then sees rotated_at set,
        revokes the family (including the winner's fresh child) and reports
        REUSE — so the stolen-token race always ends with a dead family.
        """
        maker = build_sessionmaker(engine)
        async with maker() as setup:
            user_id = await _create_user(setup)
            grant = await create_session(setup, user_id=user_id, clock=frozen_clock)
            await setup.commit()

        async def racer():
            async with maker() as racing_session:
                result = await rotate_session(
                    racing_session, token=grant.token, clock=lambda: LATER
                )
                await racing_session.commit()
                return result

        try:
            results = await asyncio.gather(racer(), racer())
            outcomes = {result.outcome for result in results}
            assert outcomes == {RotateOutcome.ROTATED, RotateOutcome.REUSE}

            (winner,) = [r for r in results if r.outcome is RotateOutcome.ROTATED]
            async with engine.connect() as conn:
                rows = await _fetch_rows(conn, user_id)
            assert len(rows) == 2
            assert all(row["revoked_at"] is not None for row in rows), (
                "the loser must revoke the whole family, winner's child included"
            )
            async with maker() as check:
                child = await rotate_session(
                    check, token=winner.grant.token, clock=lambda: EVEN_LATER
                )
                assert child.outcome is RotateOutcome.REVOKED, (
                    "security-first: the winner's child token must be unusable"
                )
        finally:
            async with maker() as cleanup:
                await cleanup.execute(
                    sa.text("DELETE FROM users WHERE id = :id"), {"id": str(user_id)}
                )
                await cleanup.commit()


class TestRevokeHelpers:
    async def test_revoke_session_family_revokes_every_active_row_in_that_family_only(
        self, session
    ):
        user_id = await _create_user(session)
        target = await create_session(session, user_id=user_id, clock=frozen_clock)
        await rotate_session(session, token=target.token, clock=frozen_clock)
        bystander = await create_session(session, user_id=user_id, clock=frozen_clock)

        count = await revoke_session_family(
            session, family_id=target.auth_session.family_id, clock=lambda: LATER
        )
        assert count == 2

        rows = await _fetch_rows(session, user_id)
        for row in rows:
            if row["family_id"] == target.auth_session.family_id:
                assert row["revoked_at"] == LATER
            else:
                assert row["revoked_at"] is None
        assert bystander.auth_session.revoked_at is None

    async def test_revoke_session_family_does_not_restamp_already_revoked_rows(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        family_id = grant.auth_session.family_id
        assert await revoke_session_family(session, family_id=family_id, clock=lambda: LATER) == 1
        assert (
            await revoke_session_family(session, family_id=family_id, clock=lambda: EVEN_LATER) == 0
        )
        (row,) = await _fetch_rows(session, user_id)
        assert row["revoked_at"] == LATER, "revoked_at must keep its original stamp"

    async def test_revoke_all_user_sessions_spans_families_but_not_other_users(self, session):
        user_id = await _create_user(session)
        other_user_id = await _create_user(session)
        first = await create_session(session, user_id=user_id, clock=frozen_clock)
        await create_session(session, user_id=user_id, clock=frozen_clock)
        await rotate_session(session, token=first.token, clock=frozen_clock)
        await create_session(session, user_id=other_user_id, clock=frozen_clock)

        count = await revoke_all_user_sessions(session, user_id=user_id, clock=lambda: LATER)
        assert count == 3

        assert all(row["revoked_at"] == LATER for row in await _fetch_rows(session, user_id))
        assert all(row["revoked_at"] is None for row in await _fetch_rows(session, other_user_id))

    async def test_revoke_helpers_flush_but_do_not_commit(self, engine, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        await revoke_session_family(
            session, family_id=grant.auth_session.family_id, clock=lambda: LATER
        )
        await revoke_all_user_sessions(session, user_id=user_id, clock=lambda: LATER)
        async with engine.connect() as conn:
            assert await _fetch_rows(conn, user_id) == [], (
                "revocation must not commit the caller's transaction"
            )


class TestCascadeDelete:
    async def test_deleting_the_user_deletes_their_sessions(self, session):
        user_id = await _create_user(session)
        await create_session(session, user_id=user_id, clock=frozen_clock)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        await rotate_session(session, token=grant.token, clock=lambda: LATER)
        assert len(await _fetch_rows(session, user_id)) == 3

        await session.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": str(user_id)})
        assert await _fetch_rows(session, user_id) == []


class TestRevokeFamilyByToken:
    """The logout helper: resolve a raw token under lock, kill its family."""

    async def test_unknown_or_malformed_tokens_resolve_to_none(self, session):
        assert await revoke_family_by_token(session, token="never-issued") is None
        for malformed in ("", "с-кириллицей", "\x00\n"):
            assert await revoke_family_by_token(session, token=malformed) is None, repr(malformed)

    async def test_active_token_revokes_every_row_in_its_family(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        rotated = await rotate_session(session, token=grant.token, clock=lambda: LATER)
        other = await create_session(session, user_id=user_id, clock=frozen_clock)

        result = await revoke_family_by_token(
            session, token=rotated.grant.token, clock=lambda: EVEN_LATER
        )

        assert result is not None
        assert result.newly_revoked == 2, "rotated parent and active child both get stamped"
        assert result.identity.user_id == user_id
        assert result.identity.family_id == grant.auth_session.family_id
        family_id = grant.auth_session.family_id
        for row in await _fetch_rows(session, user_id):
            if row["family_id"] == family_id:
                assert row["revoked_at"] == EVEN_LATER
            else:
                assert row["revoked_at"] is None, "other families must stay untouched"
        assert other.token != rotated.grant.token

    async def test_rotated_parent_token_still_resolves_and_kills_the_family(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        await rotate_session(session, token=grant.token, clock=lambda: LATER)

        result = await revoke_family_by_token(session, token=grant.token, clock=lambda: LATER)

        assert result is not None
        assert result.newly_revoked == 2
        assert all(row["revoked_at"] == LATER for row in await _fetch_rows(session, user_id))

    async def test_already_revoked_family_reports_zero_newly_revoked(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        first = await revoke_family_by_token(session, token=grant.token, clock=lambda: LATER)
        assert first is not None and first.newly_revoked == 1

        second = await revoke_family_by_token(session, token=grant.token, clock=lambda: LATER)

        assert second is not None
        assert second.newly_revoked == 0, "idempotent: nothing left to stamp"
        assert second.identity.family_id == first.identity.family_id
        (row,) = await _fetch_rows(session, user_id)
        assert row["revoked_at"] == LATER, "the original stamp must not move"

    async def test_result_is_frozen_and_never_leaks_the_raw_token(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        result = await revoke_family_by_token(session, token=grant.token, clock=lambda: LATER)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.newly_revoked = 0
        assert grant.token not in repr(result)
        assert grant.token not in repr(result.identity)


class TestRotationIdentity:
    """Rotation outcomes expose a safe, token-free identity for auditing."""

    async def test_rotated_outcome_carries_the_family_identity(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        result = await rotate_session(session, token=grant.token, clock=lambda: LATER)
        assert result.outcome is RotateOutcome.ROTATED
        assert result.identity is not None
        assert result.identity.user_id == user_id
        assert result.identity.family_id == grant.auth_session.family_id
        assert result.identity.expires_at == FROZEN_NOW + timedelta(days=30)

    async def test_reuse_outcome_carries_identity_for_the_breach_audit(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        await rotate_session(session, token=grant.token, clock=lambda: LATER)
        reuse = await rotate_session(session, token=grant.token, clock=lambda: EVEN_LATER)
        assert reuse.outcome is RotateOutcome.REUSE
        assert reuse.identity is not None
        assert reuse.identity.user_id == user_id
        assert reuse.identity.family_id == grant.auth_session.family_id

    async def test_unknown_outcome_has_no_identity(self, session):
        result = await rotate_session(session, token="never-issued", clock=frozen_clock)
        assert result.identity is None

    async def test_identity_repr_never_leaks_tokens(self, session):
        user_id = await _create_user(session)
        grant = await create_session(session, user_id=user_id, clock=frozen_clock)
        result = await rotate_session(session, token=grant.token, clock=lambda: LATER)
        assert grant.token not in repr(result.identity)
        assert result.grant.token not in repr(result.identity)
