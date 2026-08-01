"""Founder demo/pilot payment endpoints (/founder/startups/{id}/payment).

Contracts under test:
- The founder explicitly picks a simulated outcome ('paid' or 'failed');
  the response and every field always identify mode='demo' — nothing may
  imply a real charge occurred.
- First simulate creates the row (201); every later call answers 200.
- A successful ('paid') payment can never regress to 'failed': that attempt
  answers a canonical 409 PAYMENT_ALREADY_PAID and changes nothing.
- Repeating the SAME outcome is idempotent: no duplicate row, unchanged
  paid_at.
- A prior 'failed' simulation can be retried to 'paid'.
- GET without ever simulating a payment is a canonical 404 PAYMENT_NOT_FOUND.
- Payment is per STARTUP: a founder with multiple startups has fully
  isolated payment state per startup.
- Once VC-visible, POST answers 409 STARTUP_LOCKED; GET stays available.
- Foreign and unknown startups share one 404 STARTUP_NOT_FOUND; VC tokens
  get 403 FORBIDDEN_ROLE; POST demands an exact allowed Origin.
- Audit rows carry only IDs, mode, and status — never an amount.
- Concurrent duplicate simulate requests for the same startup never create
  two payment rows.
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa

from app.db import build_engine, build_sessionmaker
from tests.integration.test_founder_startups import (
    assert_error_envelope,
    create_startup,
    founder_headers,
    open_client,
    seed_user,
)

PAYMENT = "/founder/startups/{}/payment"


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def client(test_database_url, db_at_head):
    async with open_client(test_database_url) as c:
        yield c


async def fetch_all(engine, query: str, **params) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(sa.text(query), params)
        return [dict(row) for row in result.mappings()]


async def run_sql(engine, query: str, **params) -> None:
    async with build_sessionmaker(engine)() as session:
        await session.execute(sa.text(query), params)
        await session.commit()


async def simulate(client, token: str, startup_id: str, outcome: str):
    return await client.post(
        PAYMENT.format(startup_id),
        json={"simulate_outcome": outcome},
        headers=founder_headers(token),
    )


async def payment_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, mode, status, label, paid_at FROM payments WHERE startup_id = :sid",
        sid=startup_id,
    )


async def payment_audit_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT action, metadata::text AS metadata_text FROM audit_log "
        "WHERE entity_id = :sid AND action LIKE 'startup.payment%' ORDER BY at, id",
        sid=startup_id,
    )


class TestSimulatePayment:
    async def test_first_paid_simulation_creates_the_row(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await simulate(client, token, startup["id"], "paid")

        assert response.status_code == 201, response.text
        body = response.json()
        assert uuid.UUID(body["id"])
        assert body["mode"] == "demo"
        assert body["status"] == "paid"
        assert body["label"] == "demo_payment"
        assert body["paid_at"]
        assert "amount" not in body
        assert "currency" not in body
        assert "provider" not in body
        rows = await payment_rows(engine, startup["id"])
        assert len(rows) == 1
        assert rows[0]["status"] == "paid"

    async def test_first_failed_simulation_creates_the_row_with_no_paid_at(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await simulate(client, token, startup["id"], "failed")

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "failed"
        assert body["paid_at"] is None

    async def test_response_never_implies_a_real_charge(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await simulate(client, token, startup["id"], "paid")
        text_lower = response.text.lower()
        for forbidden in ("charged your card", "transaction id", "receipt", "invoice"):
            assert forbidden not in text_lower

    async def test_repeating_the_same_outcome_is_idempotent(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        first = await simulate(client, token, startup["id"], "paid")
        assert first.status_code == 201
        first_paid_at = first.json()["paid_at"]

        second = await simulate(client, token, startup["id"], "paid")

        assert second.status_code == 200, second.text
        assert second.json()["paid_at"] == first_paid_at
        assert len(await payment_rows(engine, startup["id"])) == 1

    async def test_repeating_failed_is_idempotent(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        assert (await simulate(client, token, startup["id"], "failed")).status_code == 201

        second = await simulate(client, token, startup["id"], "failed")

        assert second.status_code == 200, second.text
        assert second.json()["status"] == "failed"
        assert len(await payment_rows(engine, startup["id"])) == 1

    async def test_failed_then_paid_retry_succeeds(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        assert (await simulate(client, token, startup["id"], "failed")).status_code == 201

        response = await simulate(client, token, startup["id"], "paid")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "paid"
        assert body["paid_at"]
        rows = await payment_rows(engine, startup["id"])
        assert len(rows) == 1
        assert rows[0]["status"] == "paid"

    async def test_paid_cannot_regress_to_failed(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        first = await simulate(client, token, startup["id"], "paid")
        assert first.status_code == 201
        paid_at = first.json()["paid_at"]

        response = await simulate(client, token, startup["id"], "failed")

        assert_error_envelope(response, 409, "PAYMENT_ALREADY_PAID")
        rows = await payment_rows(engine, startup["id"])
        assert len(rows) == 1
        assert rows[0]["status"] == "paid"
        assert rows[0]["paid_at"] is not None

        get_response = await client.get(
            PAYMENT.format(startup["id"]), headers=founder_headers(token)
        )
        assert get_response.json()["paid_at"] == paid_at

    async def test_invalid_outcome_is_rejected_and_changes_nothing(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await client.post(
            PAYMENT.format(startup["id"]),
            json={"simulate_outcome": "pending"},
            headers=founder_headers(token),
        )

        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert await payment_rows(engine, startup["id"]) == []

    async def test_extra_fields_are_rejected(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await client.post(
            PAYMENT.format(startup["id"]),
            json={"simulate_outcome": "paid", "amount": 100},
            headers=founder_headers(token),
        )

        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert await payment_rows(engine, startup["id"]) == []

    async def test_concurrent_duplicate_simulations_create_one_row(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        responses = await asyncio.gather(
            *(simulate(client, token, startup["id"], "paid") for _ in range(5))
        )

        assert all(r.status_code in (200, 201) for r in responses), [r.text for r in responses]
        assert sum(1 for r in responses if r.status_code == 201) == 1
        rows = await payment_rows(engine, startup["id"])
        assert len(rows) == 1
        assert rows[0]["status"] == "paid"


class TestGetPayment:
    async def test_get_without_a_payment_is_a_canonical_404(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await client.get(PAYMENT.format(startup["id"]), headers=founder_headers(token))
        assert_error_envelope(response, 404, "PAYMENT_NOT_FOUND")

    async def test_get_reports_the_current_payment(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await simulate(client, token, startup["id"], "paid")

        response = await client.get(PAYMENT.format(startup["id"]), headers=founder_headers(token))

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "paid"
        assert body["mode"] == "demo"

    async def test_get_stays_available_when_the_startup_is_locked(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await simulate(client, token, startup["id"], "paid")
        await run_sql(
            engine, "UPDATE startups SET vc_visible_at = now() WHERE id = :id", id=startup["id"]
        )
        response = await client.get(PAYMENT.format(startup["id"]), headers=founder_headers(token))
        assert response.status_code == 200


class TestMultiStartupIsolation:
    async def test_payments_are_isolated_per_startup(self, client, engine):
        _, token = await seed_user(engine)
        first = await create_startup(client, token)
        second = await create_startup(client, token)

        await simulate(client, token, first["id"], "paid")
        await simulate(client, token, second["id"], "failed")

        first_get = await client.get(PAYMENT.format(first["id"]), headers=founder_headers(token))
        second_get = await client.get(PAYMENT.format(second["id"]), headers=founder_headers(token))
        assert first_get.json()["status"] == "paid"
        assert second_get.json()["status"] == "failed"

    async def test_editing_a_startup_after_payment_does_not_change_it(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await simulate(client, token, startup["id"], "paid")

        await client.patch(
            f"/founder/startups/{startup['id']}",
            json={"name": "Renamed"},
            headers=founder_headers(token),
        )

        response = await client.get(PAYMENT.format(startup["id"]), headers=founder_headers(token))
        assert response.json()["status"] == "paid"


class TestLockedStartups:
    @pytest.mark.parametrize(
        "lock_sql",
        [
            "UPDATE startups SET vc_visible_at = now() WHERE id = :id",
            "UPDATE startups SET status = 'vc_visible' WHERE id = :id",
        ],
    )
    async def test_simulate_on_a_locked_startup_answers_409(self, client, engine, lock_sql):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await run_sql(engine, lock_sql, id=startup["id"])

        response = await simulate(client, token, startup["id"], "paid")

        assert_error_envelope(response, 409, "STARTUP_LOCKED")
        assert await payment_rows(engine, startup["id"]) == []


class TestOwnershipAndRoles:
    async def test_foreign_and_unknown_startups_share_one_404(self, client, engine):
        _, owner_token = await seed_user(engine)
        _, other_token = await seed_user(engine)
        startup = await create_startup(client, owner_token)

        for startup_id in (startup["id"], str(uuid.uuid4())):
            post_response = await simulate(client, other_token, startup_id, "paid")
            assert_error_envelope(post_response, 404, "STARTUP_NOT_FOUND")
            get_response = await client.get(
                PAYMENT.format(startup_id), headers=founder_headers(other_token)
            )
            assert_error_envelope(get_response, 404, "STARTUP_NOT_FOUND")

    async def test_vc_tokens_are_refused_on_every_route(self, client, engine):
        _, founder_token = await seed_user(engine)
        _, vc_token = await seed_user(engine, role="vc")
        startup = await create_startup(client, founder_token)

        path = PAYMENT.format(startup["id"])
        headers = founder_headers(vc_token)
        post_response = await client.post(path, json={"simulate_outcome": "paid"}, headers=headers)
        get_response = await client.get(path, headers=headers)
        assert_error_envelope(post_response, 403, "FORBIDDEN_ROLE")
        assert_error_envelope(get_response, 403, "FORBIDDEN_ROLE")

    async def test_missing_token_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await client.get(PAYMENT.format(startup["id"]))
        assert_error_envelope(response, 401, "AUTH_TOKEN_INVALID")


class TestOriginPolicy:
    @pytest.mark.parametrize("origin", [None, "https://evil.example"])
    async def test_post_demands_an_exact_allowed_origin(self, client, engine, origin):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await client.post(
            PAYMENT.format(startup["id"]),
            json={"simulate_outcome": "paid"},
            headers=founder_headers(token, origin=origin),
        )
        assert_error_envelope(response, 403, "FORBIDDEN_ORIGIN")
        assert await payment_rows(engine, startup["id"]) == []

    async def test_reads_stay_origin_free(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await simulate(client, token, startup["id"], "paid")
        response = await client.get(
            PAYMENT.format(startup["id"]), headers=founder_headers(token, origin=None)
        )
        assert response.status_code == 200


class TestAuditTrail:
    async def test_simulate_is_audited_with_safe_metadata_only(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        await simulate(client, token, startup["id"], "failed")
        await simulate(client, token, startup["id"], "paid")

        rows = await payment_audit_rows(engine, startup["id"])
        assert [row["action"] for row in rows] == [
            "startup.payment_simulated_failed",
            "startup.payment_simulated_paid",
        ]
        for row in rows:
            assert '"payment_mode": "demo"' in row["metadata_text"]
            assert "amount" not in row["metadata_text"]
            assert "currency" not in row["metadata_text"]

    async def test_idempotent_repeat_does_not_duplicate_the_audit_row(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await simulate(client, token, startup["id"], "paid")
        await simulate(client, token, startup["id"], "paid")

        rows = await payment_audit_rows(engine, startup["id"])
        assert len(rows) == 1
