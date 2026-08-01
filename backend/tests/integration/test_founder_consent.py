"""Founder AI/privacy consent endpoints (/founder/startups/{id}/consents).

Contracts under test:
- POST grants consent at a specific kind/text_version; only the server's
  CURRENT_AI_PRIVACY_VERSION is accepted — stale/unknown versions answer the
  canonical 422 CONSENT_VERSION_INVALID.
- Granting again at an already-granted version is idempotent (200, same
  row, no duplicate); a genuinely new text_version is a fresh row (201) that
  preserves the earlier version's row untouched.
- GET returns a summary (current_version, whether it is granted) plus the
  full grant history, for frontend hydration.
- Consent is per STARTUP: a founder with multiple startups has fully
  isolated consent state per startup.
- Once VC-visible, POST answers 409 STARTUP_LOCKED; GET stays available.
- Foreign and unknown startups share one 404 STARTUP_NOT_FOUND; VC tokens
  get 403 FORBIDDEN_ROLE; POST demands an exact allowed Origin.
- Audit rows carry only IDs, kind, and text_version — never policy text.
- Editing the startup after granting consent never revokes it.
- Concurrent duplicate grant requests for the same startup/version never
  create two rows.
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa

from app.db import build_engine, build_sessionmaker
from app.models.consent import CURRENT_AI_PRIVACY_VERSION
from tests.integration.test_founder_startups import (
    assert_error_envelope,
    create_startup,
    founder_headers,
    open_client,
    seed_user,
)

CONSENTS = "/founder/startups/{}/consents"


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


async def grant(client, token: str, startup_id: str, *, kind="ai_privacy", text_version=None):
    version = CURRENT_AI_PRIVACY_VERSION if text_version is None else text_version
    return await client.post(
        CONSENTS.format(startup_id),
        json={"kind": kind, "text_version": version},
        headers=founder_headers(token),
    )


async def consent_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, kind, text_version FROM consents WHERE startup_id = :sid",
        sid=startup_id,
    )


async def consent_audit_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT action, metadata::text AS metadata_text FROM audit_log "
        "WHERE entity_id = :sid AND action LIKE 'startup.consent%' ORDER BY at, id",
        sid=startup_id,
    )


class TestGrantConsent:
    async def test_first_grant_creates_the_row(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await grant(client, token, startup["id"])

        assert response.status_code == 201, response.text
        body = response.json()
        assert uuid.UUID(body["id"])
        assert body["kind"] == "ai_privacy"
        assert body["text_version"] == CURRENT_AI_PRIVACY_VERSION
        assert body["granted_at"]
        rows = await consent_rows(engine, startup["id"])
        assert len(rows) == 1

    async def test_repeated_grant_at_same_version_is_idempotent(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        first = await grant(client, token, startup["id"])
        assert first.status_code == 201

        second = await grant(client, token, startup["id"])

        assert second.status_code == 200, second.text
        assert second.json()["id"] == first.json()["id"]
        assert len(await consent_rows(engine, startup["id"])) == 1

    async def test_unknown_version_is_rejected_and_changes_nothing(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await grant(client, token, startup["id"], text_version="ai-privacy.v0")

        assert_error_envelope(response, 422, "CONSENT_VERSION_INVALID")
        assert await consent_rows(engine, startup["id"]) == []

    async def test_unknown_kind_is_rejected_by_request_validation(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await grant(client, token, startup["id"], kind="marketing")

        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert await consent_rows(engine, startup["id"]) == []

    async def test_extra_fields_are_rejected(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await client.post(
            CONSENTS.format(startup["id"]),
            json={
                "kind": "ai_privacy",
                "text_version": CURRENT_AI_PRIVACY_VERSION,
                "accepted_by_ip": "1.2.3.4",
            },
            headers=founder_headers(token),
        )

        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        assert await consent_rows(engine, startup["id"]) == []

    async def test_blank_text_version_is_rejected(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await grant(client, token, startup["id"], text_version="")

        assert response.status_code == 422
        assert await consent_rows(engine, startup["id"]) == []

    async def test_concurrent_duplicate_grants_create_one_row(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        responses = await asyncio.gather(*(grant(client, token, startup["id"]) for _ in range(5)))

        assert all(r.status_code in (200, 201) for r in responses), [r.text for r in responses]
        assert sum(1 for r in responses if r.status_code == 201) == 1
        assert len(await consent_rows(engine, startup["id"])) == 1


class TestGetConsents:
    async def test_get_with_no_grants_reports_ungranted_and_empty_history(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        response = await client.get(CONSENTS.format(startup["id"]), headers=founder_headers(token))

        assert response.status_code == 200
        body = response.json()
        assert body["current_version"] == CURRENT_AI_PRIVACY_VERSION
        assert body["granted"] is False
        assert body["history"] == []

    async def test_get_after_grant_reports_granted_and_history(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await grant(client, token, startup["id"])

        response = await client.get(CONSENTS.format(startup["id"]), headers=founder_headers(token))

        body = response.json()
        assert body["granted"] is True
        assert len(body["history"]) == 1
        assert body["history"][0]["text_version"] == CURRENT_AI_PRIVACY_VERSION

    async def test_get_stays_available_when_the_startup_is_locked(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await grant(client, token, startup["id"])
        await run_sql(
            engine, "UPDATE startups SET vc_visible_at = now() WHERE id = :id", id=startup["id"]
        )
        response = await client.get(CONSENTS.format(startup["id"]), headers=founder_headers(token))
        assert response.status_code == 200
        assert response.json()["granted"] is True


class TestMultiStartupIsolation:
    async def test_consents_are_isolated_per_startup(self, client, engine):
        _, token = await seed_user(engine)
        first = await create_startup(client, token)
        second = await create_startup(client, token)

        await grant(client, token, first["id"])

        first_get = await client.get(CONSENTS.format(first["id"]), headers=founder_headers(token))
        second_get = await client.get(CONSENTS.format(second["id"]), headers=founder_headers(token))
        assert first_get.json()["granted"] is True
        assert second_get.json()["granted"] is False

    async def test_editing_a_startup_after_consent_does_not_revoke_it(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await grant(client, token, startup["id"])

        await client.patch(
            f"/founder/startups/{startup['id']}",
            json={"name": "Renamed"},
            headers=founder_headers(token),
        )

        response = await client.get(CONSENTS.format(startup["id"]), headers=founder_headers(token))
        assert response.json()["granted"] is True


class TestLockedStartups:
    @pytest.mark.parametrize(
        "lock_sql",
        [
            "UPDATE startups SET vc_visible_at = now() WHERE id = :id",
            "UPDATE startups SET status = 'vc_visible' WHERE id = :id",
        ],
    )
    async def test_grant_on_a_locked_startup_answers_409(self, client, engine, lock_sql):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await run_sql(engine, lock_sql, id=startup["id"])

        response = await grant(client, token, startup["id"])

        assert_error_envelope(response, 409, "STARTUP_LOCKED")
        assert await consent_rows(engine, startup["id"]) == []


class TestOwnershipAndRoles:
    async def test_foreign_and_unknown_startups_share_one_404(self, client, engine):
        _, owner_token = await seed_user(engine)
        _, other_token = await seed_user(engine)
        startup = await create_startup(client, owner_token)

        for startup_id in (startup["id"], str(uuid.uuid4())):
            post_response = await grant(client, other_token, startup_id)
            assert_error_envelope(post_response, 404, "STARTUP_NOT_FOUND")
            get_response = await client.get(
                CONSENTS.format(startup_id), headers=founder_headers(other_token)
            )
            assert_error_envelope(get_response, 404, "STARTUP_NOT_FOUND")

    async def test_vc_tokens_are_refused_on_every_route(self, client, engine):
        _, founder_token = await seed_user(engine)
        _, vc_token = await seed_user(engine, role="vc")
        startup = await create_startup(client, founder_token)

        path = CONSENTS.format(startup["id"])
        headers = founder_headers(vc_token)
        post_response = await client.post(
            path,
            json={"kind": "ai_privacy", "text_version": CURRENT_AI_PRIVACY_VERSION},
            headers=headers,
        )
        get_response = await client.get(path, headers=headers)
        assert_error_envelope(post_response, 403, "FORBIDDEN_ROLE")
        assert_error_envelope(get_response, 403, "FORBIDDEN_ROLE")

    async def test_missing_token_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await client.get(CONSENTS.format(startup["id"]))
        assert_error_envelope(response, 401, "AUTH_TOKEN_INVALID")


class TestOriginPolicy:
    @pytest.mark.parametrize("origin", [None, "https://evil.example"])
    async def test_post_demands_an_exact_allowed_origin(self, client, engine, origin):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await client.post(
            CONSENTS.format(startup["id"]),
            json={"kind": "ai_privacy", "text_version": CURRENT_AI_PRIVACY_VERSION},
            headers=founder_headers(token, origin=origin),
        )
        assert_error_envelope(response, 403, "FORBIDDEN_ORIGIN")
        assert await consent_rows(engine, startup["id"]) == []

    async def test_reads_stay_origin_free(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await grant(client, token, startup["id"])
        response = await client.get(
            CONSENTS.format(startup["id"]), headers=founder_headers(token, origin=None)
        )
        assert response.status_code == 200


class TestAuditTrail:
    async def test_grant_is_audited_with_safe_metadata_only(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)

        await grant(client, token, startup["id"])

        rows = await consent_audit_rows(engine, startup["id"])
        assert [row["action"] for row in rows] == ["startup.consent_grant"]
        assert f'"text_version": "{CURRENT_AI_PRIVACY_VERSION}"' in rows[0]["metadata_text"]
        assert '"kind": "ai_privacy"' in rows[0]["metadata_text"]

    async def test_idempotent_repeat_does_not_duplicate_the_audit_row(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await grant(client, token, startup["id"])
        await grant(client, token, startup["id"])

        rows = await consent_audit_rows(engine, startup["id"])
        assert len(rows) == 1
