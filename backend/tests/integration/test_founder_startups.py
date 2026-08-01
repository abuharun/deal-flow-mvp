"""Founder startup + submission endpoints (/founder/startups).

Contracts under test:
- A founder account owns and manages MULTIPLE startups; POST creates the
  startup and its empty submission in one transaction.
- GET list returns metadata for the current founder only; founders are fully
  isolated from each other, and an unknown or foreign startup_id answers a
  safe canonical 404 STARTUP_NOT_FOUND (never 403 — existence must not leak).
- VC tokens are refused with the canonical 403 FORBIDDEN_ROLE on every route.
- PATCHes bump the monotonically increasing input_revision exactly once per
  material transaction; a no-op patch changes nothing and bumps nothing.
- Submit validates completeness explicitly; a submitted startup remains
  editable, a VC-visible one answers the canonical 409 STARTUP_LOCKED.
- dataroom_url accepts only normalized safe http(s) URLs; validation errors
  never echo submitted values.
- Audit rows carry only IDs, action, status, and input_revision — never
  answers, URLs, or financial values.
- State-changing endpoints demand an exact allowed Origin (same policy as the
  cookie-bound auth routes); reads stay origin-free.
"""

import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
import sqlalchemy as sa

from app.config import Settings
from app.db import build_engine, build_sessionmaker
from app.main import create_app
from app.models import UserRole
from app.security.passwords import hash_password
from app.security.tokens import create_access_token

PASSWORD = "correct-horse-battery-staple"
JWT_SECRET = "test-startups-jwt-secret-0123456789abcdef0123456789abcdef"
ORIGIN = "http://localhost:5173"

PASSWORD_HASH = hash_password(PASSWORD)

STARTUPS = "/founder/startups"

ANSWER_FIELDS = ("problem", "product", "market", "traction", "team", "ask")

COMPLETE_ANSWERS = {
    "problem": "Freight brokers in Central Asia still run on phone calls.",
    "product": "A marketplace app matching shippers with vetted carriers.",
    "market": "The Uzbek logistics market moves $2B of freight per year.",
    "traction": "120 weekly active brokers, 40% month-over-month growth.",
    "team": "Two ex-Yandex engineers and a logistics operator.",
    "ask": "Raising a seed round to expand into Kazakhstan.",
}


def unique_email(prefix: str = "startup") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def build_app(database_url: str):
    settings = Settings(
        _env_file=None,
        env="test",
        database_url=database_url,
        jwt_secret=JWT_SECRET,
        frontend_origins=(ORIGIN,),
    )
    return create_app(settings)


@asynccontextmanager
async def open_client(database_url: str, *, raise_app_exceptions: bool = True):
    app = build_app(database_url)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def client(test_database_url, db_at_head):
    async with open_client(test_database_url) as c:
        yield c


async def seed_user(engine, *, role: str = "founder") -> tuple[uuid.UUID, str]:
    """Insert a verified user and mint a matching access token."""
    async with build_sessionmaker(engine)() as session:
        result = await session.execute(
            sa.text(
                "INSERT INTO users (email, password_hash, full_name, role, email_verified_at) "
                "VALUES (:email, :password_hash, 'Startup Tester', CAST(:role AS user_role), "
                "now()) RETURNING id"
            ),
            {"email": unique_email(role), "password_hash": PASSWORD_HASH, "role": role},
        )
        user_id = result.scalar_one()
        await session.commit()
    token = create_access_token(user_id=user_id, role=UserRole(role), secret=JWT_SECRET)
    return user_id, token


async def fetch_all(engine, query: str, **params) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(sa.text(query), params)
        return [dict(row) for row in result.mappings()]


def founder_headers(token: str, *, origin: str | None = ORIGIN) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if origin is not None:
        headers["Origin"] = origin
    return headers


async def create_startup(client, token: str, *, name: str | None = None, **fields) -> dict:
    payload = {"name": name or f"Startup {uuid.uuid4().hex[:8]}", **fields}
    response = await client.post(STARTUPS, json=payload, headers=founder_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


def assert_error_envelope(response: httpx.Response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"error"}, "errors must use only the canonical envelope"
    error = body["error"]
    assert error["code"] == code
    assert error["message_key"].startswith("errors.")
    assert error["request_id"]
    return error


class TestCreateStartup:
    async def test_create_returns_a_draft_with_an_empty_submission(self, client, engine):
        founder_id, token = await seed_user(engine)

        response = await client.post(
            STARTUPS,
            json={"name": "Aral Robotics", "one_liner": "Robots for cotton farms"},
            headers=founder_headers(token),
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert uuid.UUID(body["id"])
        assert body["name"] == "Aral Robotics"
        assert body["one_liner"] == "Robots for cotton farms"
        assert body["sector"] == ""
        assert body["status"] == "draft"
        assert body["input_revision"] == 1
        assert body["submitted_at"] is None
        assert body["vc_visible_at"] is None
        submission = body["submission"]
        for field in ANSWER_FIELDS:
            assert submission[field] == "", field
        assert submission["revenue"] is None
        assert submission["ask_amount"] is None
        assert submission["dataroom_url"] is None
        assert submission["completed_steps"] == []
        assert "founder_id" not in body, "internal ownership ids stay out of the payload"

    async def test_create_persists_startup_and_submission_rows_together(self, client, engine):
        founder_id, token = await seed_user(engine)
        body = await create_startup(client, token)

        startups = await fetch_all(engine, "SELECT * FROM startups WHERE id = :id", id=body["id"])
        assert len(startups) == 1
        assert str(startups[0]["founder_id"]) == str(founder_id)
        assert startups[0]["status"] == "draft"
        assert startups[0]["input_revision"] == 1

        submissions = await fetch_all(
            engine, "SELECT * FROM submissions WHERE startup_id = :id", id=body["id"]
        )
        assert len(submissions) == 1, "the empty submission is created in the same transaction"
        assert submissions[0]["problem"] == ""

    async def test_a_founder_can_create_multiple_startups(self, client, engine):
        founder_id, token = await seed_user(engine)

        first = await create_startup(client, token, name="First Venture")
        second = await create_startup(client, token, name="Second Venture")

        assert first["id"] != second["id"]
        rows = await fetch_all(
            engine,
            "SELECT id FROM startups WHERE founder_id = :founder_id",
            founder_id=str(founder_id),
        )
        assert len(rows) == 2

    async def test_blank_name_is_rejected_without_creating_anything(self, client, engine):
        founder_id, token = await seed_user(engine)

        response = await client.post(STARTUPS, json={"name": "   "}, headers=founder_headers(token))

        assert_error_envelope(response, 422, "VALIDATION_FAILED")
        rows = await fetch_all(
            engine,
            "SELECT id FROM startups WHERE founder_id = :founder_id",
            founder_id=str(founder_id),
        )
        assert rows == []


class TestListAndGet:
    async def test_list_returns_only_the_current_founders_startups(self, client, engine):
        _, token_a = await seed_user(engine)
        _, token_b = await seed_user(engine)
        mine = await create_startup(client, token_a, name="Mine One")
        await create_startup(client, token_b, name="Theirs")

        response = await client.get(STARTUPS, headers=founder_headers(token_a, origin=None))

        assert response.status_code == 200, response.text
        ids = [item["id"] for item in response.json()]
        assert ids == [mine["id"]], "founders must be fully isolated from each other"

    async def test_list_is_metadata_only(self, client, engine):
        _, token = await seed_user(engine)
        await create_startup(client, token)

        response = await client.get(STARTUPS, headers=founder_headers(token, origin=None))

        (item,) = response.json()
        assert "submission" not in item
        assert "founder_id" not in item
        assert item["status"] == "draft"
        assert item["input_revision"] == 1

    async def test_get_returns_the_hydrated_startup_with_submission(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token, name="Hydrated Co")

        response = await client.get(
            f"{STARTUPS}/{created['id']}", headers=founder_headers(token, origin=None)
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == created["id"]
        assert body["name"] == "Hydrated Co"
        assert body["submission"]["problem"] == ""
        assert body["submission"]["completed_steps"] == []

    async def test_foreign_and_unknown_ids_share_one_safe_404(self, client, engine):
        _, token_a = await seed_user(engine)
        _, token_b = await seed_user(engine)
        theirs = await create_startup(client, token_b, name="Not Yours")
        request_id = "compare-startup-404s"

        foreign = await client.get(
            f"{STARTUPS}/{theirs['id']}",
            headers={**founder_headers(token_a, origin=None), "X-Request-ID": request_id},
        )
        unknown = await client.get(
            f"{STARTUPS}/{uuid.uuid4()}",
            headers={**founder_headers(token_a, origin=None), "X-Request-ID": request_id},
        )

        assert_error_envelope(foreign, 404, "STARTUP_NOT_FOUND")
        assert_error_envelope(unknown, 404, "STARTUP_NOT_FOUND")
        assert foreign.content == unknown.content, (
            "a foreign startup must be indistinguishable from a nonexistent one (never 403)"
        )

    async def test_vc_tokens_are_forbidden_on_every_founder_route(self, client, engine):
        _, founder_token = await seed_user(engine)
        created = await create_startup(client, founder_token)
        _, vc_token = await seed_user(engine, role="vc")

        attempts = [
            client.post(STARTUPS, json={"name": "VC Co"}, headers=founder_headers(vc_token)),
            client.get(STARTUPS, headers=founder_headers(vc_token, origin=None)),
            client.get(
                f"{STARTUPS}/{created['id']}", headers=founder_headers(vc_token, origin=None)
            ),
            client.patch(
                f"{STARTUPS}/{created['id']}",
                json={"name": "VC Rename"},
                headers=founder_headers(vc_token),
            ),
            client.patch(
                f"{STARTUPS}/{created['id']}/submission",
                json={"problem": "vc edit"},
                headers=founder_headers(vc_token),
            ),
            client.post(f"{STARTUPS}/{created['id']}/submit", headers=founder_headers(vc_token)),
        ]
        for attempt in attempts:
            assert_error_envelope(await attempt, 403, "FORBIDDEN_ROLE")


class TestPatchStartup:
    async def test_material_patch_updates_fields_and_bumps_revision_once(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token, name="Old Name")

        response = await client.patch(
            f"{STARTUPS}/{created['id']}",
            json={"name": "New Name", "sector": "logistics", "city": "Tashkent"},
            headers=founder_headers(token),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["name"] == "New Name"
        assert body["sector"] == "logistics"
        assert body["city"] == "Tashkent"
        assert body["input_revision"] == 2, "one material transaction bumps the revision once"
        assert body["status"] == "draft"

    async def test_noop_patch_does_not_bump_the_revision(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token, name="Stable Name")
        first = await client.patch(
            f"{STARTUPS}/{created['id']}",
            json={"name": "Renamed"},
            headers=founder_headers(token),
        )
        assert first.json()["input_revision"] == 2

        same_values = await client.patch(
            f"{STARTUPS}/{created['id']}",
            json={"name": "Renamed"},
            headers=founder_headers(token),
        )
        empty = await client.patch(
            f"{STARTUPS}/{created['id']}", json={}, headers=founder_headers(token)
        )

        assert same_values.status_code == 200
        assert same_values.json()["input_revision"] == 2, "a no-op patch must not increment"
        assert empty.status_code == 200
        assert empty.json()["input_revision"] == 2

    async def test_patching_a_foreign_startup_is_a_safe_404(self, client, engine):
        _, token_a = await seed_user(engine)
        _, token_b = await seed_user(engine)
        theirs = await create_startup(client, token_b)

        response = await client.patch(
            f"{STARTUPS}/{theirs['id']}",
            json={"name": "Hijacked"},
            headers=founder_headers(token_a),
        )

        assert_error_envelope(response, 404, "STARTUP_NOT_FOUND")
        rows = await fetch_all(engine, "SELECT name FROM startups WHERE id = :id", id=theirs["id"])
        assert rows[0]["name"] != "Hijacked"

    async def test_blank_null_and_unknown_fields_are_rejected(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)

        for payload in ({"name": "   "}, {"name": None}, {"funding": "seed"}):
            response = await client.patch(
                f"{STARTUPS}/{created['id']}", json=payload, headers=founder_headers(token)
            )
            assert_error_envelope(response, 422, "VALIDATION_FAILED")

        rows = await fetch_all(
            engine, "SELECT input_revision FROM startups WHERE id = :id", id=created["id"]
        )
        assert rows[0]["input_revision"] == 1


class TestPatchSubmission:
    async def test_autosaving_answers_persists_and_bumps_revision_once(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)

        response = await client.patch(
            f"{STARTUPS}/{created['id']}/submission",
            json={
                "problem": COMPLETE_ANSWERS["problem"],
                "traction": COMPLETE_ANSWERS["traction"],
                "ask_amount": 500_000,
                "completed_steps": ["problem", "traction"],
            },
            headers=founder_headers(token),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["input_revision"] == 2, "one autosave transaction bumps the revision once"
        assert body["submission"]["problem"] == COMPLETE_ANSWERS["problem"]
        assert body["submission"]["traction"] == COMPLETE_ANSWERS["traction"]
        assert body["submission"]["ask_amount"] == 500_000
        assert body["submission"]["completed_steps"] == ["problem", "traction"]
        assert body["submission"]["product"] == "", "untouched answers stay untouched"

    async def test_progress_only_patch_persists_without_bumping_revision(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)

        response = await client.patch(
            f"{STARTUPS}/{created['id']}/submission",
            json={"completed_steps": ["problem"]},
            headers=founder_headers(token),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["submission"]["completed_steps"] == ["problem"]
        assert body["input_revision"] == 1, (
            "step bookkeeping is progress, not material founder input"
        )

    async def test_noop_submission_patch_does_not_bump_revision(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)
        first = await client.patch(
            f"{STARTUPS}/{created['id']}/submission",
            json={"problem": "We solve X."},
            headers=founder_headers(token),
        )
        assert first.json()["input_revision"] == 2

        repeat = await client.patch(
            f"{STARTUPS}/{created['id']}/submission",
            json={"problem": "We solve X."},
            headers=founder_headers(token),
        )

        assert repeat.status_code == 200
        assert repeat.json()["input_revision"] == 2, "a no-op autosave must not increment"

    async def test_nullable_financials_can_be_cleared_but_answers_cannot_be_null(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)
        await client.patch(
            f"{STARTUPS}/{created['id']}/submission",
            json={"revenue": "USD 10k MRR", "ask_amount": 250_000},
            headers=founder_headers(token),
        )

        cleared = await client.patch(
            f"{STARTUPS}/{created['id']}/submission",
            json={"revenue": None, "ask_amount": None},
            headers=founder_headers(token),
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["submission"]["revenue"] is None
        assert cleared.json()["submission"]["ask_amount"] is None

        null_answer = await client.patch(
            f"{STARTUPS}/{created['id']}/submission",
            json={"problem": None},
            headers=founder_headers(token),
        )
        assert_error_envelope(null_answer, 422, "VALIDATION_FAILED")

    async def test_dataroom_url_is_normalized_when_safe(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)

        response = await client.patch(
            f"{STARTUPS}/{created['id']}/submission",
            json={"dataroom_url": "HTTPS://Drive.Example.COM/room/AbC?usp=1"},
            headers=founder_headers(token),
        )

        assert response.status_code == 200, response.text
        assert (
            response.json()["submission"]["dataroom_url"]
            == "https://drive.example.com/room/AbC?usp=1"
        )

    async def test_unsafe_dataroom_urls_are_rejected_and_never_echoed(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)
        unsafe = [
            "javascript:alert(1)",
            "ftp://files.example.com/room",
            "https://user:hunter2@drive.example.com/room",
            "https://drive.example.com/room#fragment",
            "https://drive.example.com/ro om",
        ]

        for url in unsafe:
            response = await client.patch(
                f"{STARTUPS}/{created['id']}/submission",
                json={"dataroom_url": url},
                headers=founder_headers(token),
            )
            assert_error_envelope(response, 422, "VALIDATION_FAILED")
            assert "hunter2" not in response.text
            assert url not in response.text, "submitted values must never be echoed"

        rows = await fetch_all(
            engine,
            "SELECT dataroom_url FROM submissions WHERE startup_id = :id",
            id=created["id"],
        )
        assert rows[0]["dataroom_url"] is None

    async def test_invalid_steps_negative_amounts_and_unknown_fields_are_rejected(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)

        payloads = [
            {"completed_steps": ["Not A Slug!"]},
            {"ask_amount": -5},
            {"secret_notes": "should not exist"},
        ]
        for payload in payloads:
            response = await client.patch(
                f"{STARTUPS}/{created['id']}/submission",
                json=payload,
                headers=founder_headers(token),
            )
            assert_error_envelope(response, 422, "VALIDATION_FAILED")

    async def test_patching_a_foreign_submission_is_a_safe_404(self, client, engine):
        _, token_a = await seed_user(engine)
        _, token_b = await seed_user(engine)
        theirs = await create_startup(client, token_b)

        response = await client.patch(
            f"{STARTUPS}/{theirs['id']}/submission",
            json={"problem": "hijack"},
            headers=founder_headers(token_a),
        )

        assert_error_envelope(response, 404, "STARTUP_NOT_FOUND")
        rows = await fetch_all(
            engine, "SELECT problem FROM submissions WHERE startup_id = :id", id=theirs["id"]
        )
        assert rows[0]["problem"] == ""


async def fill_answers(client, token: str, startup_id: str, **overrides) -> dict:
    payload = {**COMPLETE_ANSWERS, **overrides}
    response = await client.patch(
        f"{STARTUPS}/{startup_id}/submission", json=payload, headers=founder_headers(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def submit(client, token: str, startup_id: str):
    return await client.post(f"{STARTUPS}/{startup_id}/submit", headers=founder_headers(token))


class TestSubmit:
    async def test_complete_submission_transitions_to_submitted_with_timestamp(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)
        filled = await fill_answers(client, token, created["id"])

        response = await submit(client, token, created["id"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "submitted"
        assert body["submitted_at"] is not None
        assert body["input_revision"] == filled["input_revision"], (
            "submitting is a lifecycle transition, not a material input change"
        )
        rows = await fetch_all(
            engine,
            "SELECT status, submitted_at FROM startups WHERE id = :id",
            id=created["id"],
        )
        assert rows[0]["status"] == "submitted"
        assert rows[0]["submitted_at"] is not None

    async def test_incomplete_submission_is_refused_naming_only_missing_fields(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)
        await fill_answers(client, token, created["id"], market="", team="   ")

        response = await submit(client, token, created["id"])

        error = assert_error_envelope(response, 422, "SUBMISSION_INCOMPLETE")
        assert "market" in error["detail"]
        assert "team" in error["detail"]
        assert "problem" not in error["detail"], "filled fields are not reported"
        for answer in COMPLETE_ANSWERS.values():
            assert answer not in response.text, "submitted values must never be echoed"
        rows = await fetch_all(
            engine,
            "SELECT status, submitted_at FROM startups WHERE id = :id",
            id=created["id"],
        )
        assert rows[0]["status"] == "draft", "a refused submit must leave the draft untouched"
        assert rows[0]["submitted_at"] is None

    async def test_submitting_twice_is_a_canonical_conflict(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)
        await fill_answers(client, token, created["id"])
        first = await submit(client, token, created["id"])
        assert first.status_code == 200

        second = await submit(client, token, created["id"])

        assert_error_envelope(second, 409, "STARTUP_ALREADY_SUBMITTED")

    async def test_submitted_startup_remains_editable_and_revision_keeps_counting(
        self, client, engine
    ):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)
        filled = await fill_answers(client, token, created["id"])
        assert (await submit(client, token, created["id"])).status_code == 200

        meta = await client.patch(
            f"{STARTUPS}/{created['id']}",
            json={"city": "Samarkand"},
            headers=founder_headers(token),
        )
        answers = await client.patch(
            f"{STARTUPS}/{created['id']}/submission",
            json={"traction": "200 weekly active brokers now."},
            headers=founder_headers(token),
        )

        assert meta.status_code == 200, meta.text
        assert answers.status_code == 200, answers.text
        assert answers.json()["input_revision"] == filled["input_revision"] + 2
        assert answers.json()["status"] == "submitted", "editing must not reset the lifecycle"

    async def test_submitting_a_foreign_startup_is_a_safe_404(self, client, engine):
        _, token_a = await seed_user(engine)
        _, token_b = await seed_user(engine)
        theirs = await create_startup(client, token_b)
        await fill_answers(client, token_b, theirs["id"])

        response = await submit(client, token_a, theirs["id"])

        assert_error_envelope(response, 404, "STARTUP_NOT_FOUND")
        rows = await fetch_all(
            engine, "SELECT status FROM startups WHERE id = :id", id=theirs["id"]
        )
        assert rows[0]["status"] == "draft"


async def execute_sql(engine, query: str, **params) -> None:
    async with engine.begin() as conn:
        await conn.execute(sa.text(query), params)


class TestVcVisibleLock:
    async def test_every_material_mutation_answers_the_canonical_409(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token, name="Locked Co")
        await fill_answers(client, token, created["id"])
        await execute_sql(
            engine,
            "UPDATE startups SET status = 'vc_visible', vc_visible_at = now() WHERE id = :id",
            id=created["id"],
        )

        attempts = [
            client.patch(
                f"{STARTUPS}/{created['id']}",
                json={"name": "Locked Rename"},
                headers=founder_headers(token),
            ),
            client.patch(
                f"{STARTUPS}/{created['id']}/submission",
                json={"problem": "locked edit"},
                headers=founder_headers(token),
            ),
            client.post(f"{STARTUPS}/{created['id']}/submit", headers=founder_headers(token)),
        ]
        for attempt in attempts:
            assert_error_envelope(await attempt, 409, "STARTUP_LOCKED")

        startups = await fetch_all(
            engine, "SELECT name, input_revision FROM startups WHERE id = :id", id=created["id"]
        )
        assert startups[0]["name"] == "Locked Co"
        submissions = await fetch_all(
            engine, "SELECT problem FROM submissions WHERE startup_id = :id", id=created["id"]
        )
        assert submissions[0]["problem"] == COMPLETE_ANSWERS["problem"]

    async def test_vc_visible_at_alone_locks_even_without_the_status(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)
        await execute_sql(
            engine,
            "UPDATE startups SET vc_visible_at = now() WHERE id = :id",
            id=created["id"],
        )

        response = await client.patch(
            f"{STARTUPS}/{created['id']}",
            json={"name": "Sneaky Rename"},
            headers=founder_headers(token),
        )

        assert_error_envelope(response, 409, "STARTUP_LOCKED")

    async def test_a_locked_startup_is_still_readable(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token)
        await execute_sql(
            engine,
            "UPDATE startups SET status = 'vc_visible', vc_visible_at = now() WHERE id = :id",
            id=created["id"],
        )

        response = await client.get(
            f"{STARTUPS}/{created['id']}", headers=founder_headers(token, origin=None)
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "vc_visible"


async def fetch_audit(engine, entity_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT action, actor_type, actor_id, entity_type, entity_id, metadata "
        "FROM audit_log WHERE entity_id = :entity_id ORDER BY at, id",
        entity_id=entity_id,
    )


class TestOriginEnforcement:
    async def test_state_changing_routes_demand_an_exact_allowed_origin(self, client, engine):
        founder_id, token = await seed_user(engine)
        created = await create_startup(client, token, name="Origin Co")

        for origin in (None, "http://evil.example", "http://localhost:5173.evil.example"):
            attempts = [
                client.post(
                    STARTUPS,
                    json={"name": "Originless"},
                    headers=founder_headers(token, origin=origin),
                ),
                client.patch(
                    f"{STARTUPS}/{created['id']}",
                    json={"name": "Originless Rename"},
                    headers=founder_headers(token, origin=origin),
                ),
                client.patch(
                    f"{STARTUPS}/{created['id']}/submission",
                    json={"problem": "originless edit"},
                    headers=founder_headers(token, origin=origin),
                ),
                client.post(
                    f"{STARTUPS}/{created['id']}/submit",
                    headers=founder_headers(token, origin=origin),
                ),
            ]
            for attempt in attempts:
                assert_error_envelope(await attempt, 403, "FORBIDDEN_ORIGIN")

        rows = await fetch_all(
            engine,
            "SELECT name, input_revision, status FROM startups WHERE founder_id = :founder_id",
            founder_id=str(founder_id),
        )
        assert rows == [{"name": "Origin Co", "input_revision": 1, "status": "draft"}], (
            "a refused Origin must not create or mutate anything"
        )


class TestAuditHygiene:
    async def test_lifecycle_actions_are_audited_with_ids_status_and_revision_only(
        self, client, engine
    ):
        founder_id, token = await seed_user(engine)
        created = await create_startup(client, token, name="Audit Co")
        await client.patch(
            f"{STARTUPS}/{created['id']}",
            json={"city": "Bukhara"},
            headers=founder_headers(token),
        )
        await fill_answers(
            client, token, created["id"], dataroom_url="https://drive.example.com/audit-room"
        )
        await client.patch(
            f"{STARTUPS}/{created['id']}/submission",
            json={"completed_steps": ["problem"]},
            headers=founder_headers(token),
        )
        assert (await submit(client, token, created["id"])).status_code == 200

        rows = await fetch_audit(engine, created["id"])

        assert [row["action"] for row in rows] == [
            "startup.create",
            "startup.update",
            "startup.submission_update",
            "startup.submission_update",
            "startup.submit",
        ]
        for row in rows:
            assert row["actor_type"] == "user"
            assert str(row["actor_id"]) == str(founder_id)
            assert row["entity_type"] == "startup"
            assert set(row["metadata"]) == {"status", "input_revision"}, (
                "audit metadata must carry ONLY status and input_revision"
            )
        assert rows[0]["metadata"] == {"status": "draft", "input_revision": 1}
        assert rows[1]["metadata"] == {"status": "draft", "input_revision": 2}
        assert rows[2]["metadata"] == {"status": "draft", "input_revision": 3}
        assert rows[3]["metadata"] == {"status": "draft", "input_revision": 3}, (
            "progress-only autosaves are audited without a revision bump"
        )
        assert rows[4]["metadata"] == {"status": "submitted", "input_revision": 3}

    async def test_audit_rows_never_contain_answers_urls_names_or_amounts(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token, name="Secret Startup Name")
        await fill_answers(
            client,
            token,
            created["id"],
            dataroom_url="https://drive.example.com/secret-room",
            ask_amount=1_234_567,
            revenue="USD 55k MRR",
        )
        assert (await submit(client, token, created["id"])).status_code == 200

        dumped = await fetch_all(
            engine,
            "SELECT (audit_log.*)::text AS row FROM audit_log WHERE entity_id = :entity_id",
            entity_id=created["id"],
        )
        blob = " ".join(row["row"] for row in dumped)
        assert blob, "the lifecycle must have produced audit rows"
        for secret in (
            "Secret Startup Name",
            "drive.example.com",
            "1234567",
            "55k",
            *COMPLETE_ANSWERS.values(),
        ):
            assert secret not in blob, f"audit trail leaked founder input: {secret!r}"

    async def test_noop_and_refused_mutations_write_no_audit_rows(self, client, engine):
        _, token = await seed_user(engine)
        created = await create_startup(client, token, name="Quiet Co")
        baseline = len(await fetch_audit(engine, created["id"]))

        await client.patch(
            f"{STARTUPS}/{created['id']}",
            json={"name": "Quiet Co"},
            headers=founder_headers(token),
        )
        await client.patch(
            f"{STARTUPS}/{created['id']}/submission",
            json={"problem": ""},
            headers=founder_headers(token),
        )
        incomplete = await submit(client, token, created["id"])
        assert incomplete.status_code == 422

        assert len(await fetch_audit(engine, created["id"])) == baseline, (
            "no-op patches and refused submits must stage no audit rows"
        )


class TestRollback:
    async def test_forced_audit_failure_rolls_back_the_whole_autosave(
        self, test_database_url, db_at_head, engine, monkeypatch
    ):
        from app.services import startup_service

        _, token = await seed_user(engine)
        async with open_client(test_database_url) as client:
            created = await create_startup(client, token, name="Atomic Co")

        async def explode(*args, **kwargs):
            raise RuntimeError("boom-secret-marker")

        monkeypatch.setattr(startup_service, "write_audit", explode)

        async with open_client(test_database_url, raise_app_exceptions=False) as client:
            response = await client.patch(
                f"{STARTUPS}/{created['id']}/submission",
                json={"problem": "should never persist"},
                headers=founder_headers(token),
            )

        assert_error_envelope(response, 500, "SERVER_ERROR")
        assert "boom-secret-marker" not in response.text
        assert "should never persist" not in response.text

        startups = await fetch_all(
            engine, "SELECT input_revision FROM startups WHERE id = :id", id=created["id"]
        )
        assert startups[0]["input_revision"] == 1, "the revision bump must roll back"
        submissions = await fetch_all(
            engine, "SELECT problem FROM submissions WHERE startup_id = :id", id=created["id"]
        )
        assert submissions[0]["problem"] == "", (
            "the mutation and its audit row must commit or roll back together"
        )
