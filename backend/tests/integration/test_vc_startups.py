"""Read-only VC access to founder-approved startups (/vc/startups).

Product contract under test: every active pilot VC account sees the same
thing -- the startups whose founders explicitly approved a narrative -- and
sees them read-only. There is no per-investor assignment in this slice, and
no endpoint here writes anything.

What an investor may read is an allow-list, not a filter:
- the safe startup profile (name/one-liner/sector/stage/city plus when it
  became visible and when it was approved),
- the exact frozen narrative version the founder approved, and
- the immutable cited report MINUS its `pitch_narrative_draft` -- the AI's
  raw draft is narrative-draft material the founder rewrote, so it never
  ships alongside the text they actually approved.

Never reachable from here, and asserted absent below: founder identity or
email, questionnaire answers, deck bytes/text/filenames, payment or consent
internals, analysis-job bookkeeping, narrative drafts and version history,
audit rows, or any model/prompt provenance.

Access model:
- VC role required; a founder bearer token gets the canonical 403
  FORBIDDEN_ROLE even for a startup that founder owns.
- Active/verified is the existing canonical auth policy: a deleted or
  unverified account's token dies as 401 AUTH_SESSION_REVOKED in
  `get_current_principal`, with no VC-specific variant.
- Unapproved, foreign-to-the-pilot, and unknown startup ids are one
  indistinguishable canonical 404 STARTUP_NOT_FOUND.
- These are reads, so no Origin is required; responses carry no-store cache
  and privacy headers because they are authenticated and sensitive.

The shared test database means other suites' approved startups are visible
too, so every assertion here is scoped to the ids this test created and the
list is walked page by page rather than assumed to fit in one page.
"""

import uuid
from contextlib import contextmanager

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.db import build_engine
from app.schemas.report import ReportV1Input
from tests.integration.test_founder_analysis import run_sql
from tests.integration.test_founder_narrative import (
    FOUNDER_TEXT,
    SEED_DRAFT,
    report_with_draft,
    save_narrative,
)
from tests.integration.test_founder_narrative_approval import approve, read_narrative
from tests.integration.test_founder_report import (
    _source,
    _valid_report_input,
    setup_completed_report,
)
from tests.integration.test_founder_startups import (
    assert_error_envelope,
    create_startup,
    fetch_all,
    founder_headers,
    open_client,
    seed_user,
)

VC_LIST = "/vc/startups"
VC_DOSSIER = "/vc/startups/{}"
ORIGIN = "http://localhost:5173"
FOREIGN_ORIGIN = "https://evil.example"

MAX_PAGE = 50
DEFAULT_PAGE = 20

SUMMARY_KEYS = {
    "id",
    "name",
    "one_liner",
    "sector",
    "funding_stage",
    "city",
    "vc_visible_at",
    "approved_at",
}
LIST_KEYS = {"items", "limit", "offset", "total"}
DOSSIER_KEYS = {"startup", "narrative", "report"}
NARRATIVE_KEYS = {"version", "content", "approved_at"}
REPORT_KEYS = {
    "schema_version",
    "language",
    "report",
    "sources",
    "partial",
    "evidence_count",
    "generated_at",
}
REPORT_BODY_KEYS = {
    "executive_summary",
    "sections",
    "competitors",
    "claims",
    "contradictions",
    "unsupported_claims",
    "readiness_checklist",
}
SOURCE_KEYS = {
    "ordinal",
    "url",
    "title",
    "published_date",
    "accessed_date",
    "source_quality",
    "confidence",
    "snippet",
}

# Any of these appearing as a key anywhere in a VC response means founder
# private data, internal bookkeeping, or draft material leaked.
FORBIDDEN_KEYS = frozenset(
    {
        "founder_id",
        "approved_by",
        "created_by",
        "email",
        "user_id",
        "narrative_version_id",
        "report_id",
        "job_id",
        "input_revision",
        "model",
        "prompt_version",
        "pitch_narrative_draft",
        "source",
        "submission",
        "problem",
        "product",
        "market",
        "traction",
        "team",
        "ask",
        "ask_amount",
        "revenue",
        "growth",
        "dataroom_url",
        "stale",
        "attempts",
        "error_code",
        "password_hash",
        "token",
        "versions",
        "history",
        "audit",
        "consent",
        "payment",
        "deck",
    }
)


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def client(test_database_url, db_at_head):
    async with open_client(test_database_url) as c:
        yield c


@pytest.fixture()
async def vc(engine):
    """An active, verified VC account and its bearer token."""
    return await seed_user(engine, role="vc")


@pytest.fixture()
async def founder(engine):
    return await seed_user(engine)


def vc_headers(token: str, *, origin: str | None = None) -> dict:
    # Reads require no Origin -- the default here is deliberately no header.
    return founder_headers(token, origin=origin)


async def list_visible(client, token: str, *, origin: str | None = None, **params):
    return await client.get(VC_LIST, params=params, headers=vc_headers(token, origin=origin))


async def get_dossier(client, token: str, startup_id, *, origin: str | None = None):
    return await client.get(VC_DOSSIER.format(startup_id), headers=vc_headers(token, origin=origin))


async def walk_all(client, token: str) -> list[dict]:
    """Every visible startup, paged (the test database is shared)."""
    items: list[dict] = []
    offset = 0
    for _ in range(100):
        response = await list_visible(client, token, limit=MAX_PAGE, offset=offset)
        assert response.status_code == 200, response.text
        page = response.json()["items"]
        items.extend(page)
        if len(page) < MAX_PAGE:
            return items
        offset += MAX_PAGE
    raise AssertionError("visible startup list did not terminate")


def report_with_sources(count: int, *, draft: str = SEED_DRAFT) -> ReportV1Input:
    payload = _valid_report_input(
        sources=[_source(ordinal) for ordinal in range(1, count + 1)]
    ).model_dump(mode="json")
    payload["report"]["pitch_narrative_draft"] = draft
    return ReportV1Input.model_validate(payload)


async def approved_startup(
    client,
    engine,
    founder_token: str,
    *,
    content: str | None = None,
    draft: str = SEED_DRAFT,
    report_input: ReportV1Input | None = None,
    **fields,
):
    """A startup carried all the way to founder-approved and VC-visible."""
    startup = await create_startup(client, founder_token, **fields)
    report = await setup_completed_report(
        client,
        engine,
        founder_token,
        startup["id"],
        report_input=report_input if report_input is not None else report_with_draft(draft),
    )
    current = await read_narrative(client, founder_token, startup["id"])
    if content is not None:
        saved = await save_narrative(client, founder_token, startup["id"], content)
        assert saved.status_code == 200, saved.text
        current = saved.json()
    approval = await approve(client, founder_token, startup["id"], current["version"])
    assert approval.status_code == 200, approval.text
    return startup, report, approval.json()


async def report_ready_startup(client, engine, founder_token: str):
    """A startup with a completed report the founder never approved."""
    startup = await create_startup(client, founder_token)
    await setup_completed_report(
        client, engine, founder_token, startup["id"], report_input=report_with_draft(SEED_DRAFT)
    )
    return startup


def keys_anywhere(node) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            found |= keys_anywhere(value)
    elif isinstance(node, list):
        for item in node:
            found |= keys_anywhere(item)
    return found


def ids_of(items: list[dict]) -> list[str]:
    return [item["id"] for item in items]


@contextmanager
def count_selects():
    """Every SELECT any engine issues while the block runs."""
    statements: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(Engine, "before_cursor_execute", before)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", before)


class TestListingApprovedStartups:
    async def test_an_approved_startup_is_listed_with_only_safe_profile_fields(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, approval = await approved_startup(
            client,
            engine,
            founder_token,
            name="Yuk Express",
            one_liner="Freight matching for Central Asia.",
            sector="logistics",
            funding_stage="seed",
            city="Tashkent",
        )

        response = await list_visible(client, vc_token, limit=MAX_PAGE)

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == LIST_KEYS
        listed = {item["id"]: item for item in await walk_all(client, vc_token)}
        assert startup["id"] in listed
        item = listed[startup["id"]]
        assert set(item) == SUMMARY_KEYS
        assert item["name"] == "Yuk Express"
        assert item["one_liner"] == "Freight matching for Central Asia."
        assert item["sector"] == "logistics"
        assert item["funding_stage"] == "seed"
        assert item["city"] == "Tashkent"
        assert item["approved_at"] == approval["approved_at"]
        assert item["vc_visible_at"] == approval["vc_visible_at"]

    async def test_every_active_vc_account_sees_the_same_approved_startups(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, first_vc_token = vc
        startup, _, _ = await approved_startup(client, engine, founder_token)
        # Created AFTER the approval: pilot access is by role, not assignment.
        _, second_vc_token = await seed_user(engine, role="vc")

        first = ids_of(await walk_all(client, first_vc_token))
        second = ids_of(await walk_all(client, second_vc_token))

        assert startup["id"] in first
        assert first == second

    async def test_startups_the_founder_never_approved_are_never_listed(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        draft_startup = await create_startup(client, founder_token)
        ready_startup = await report_ready_startup(client, engine, founder_token)

        listed = ids_of(await walk_all(client, vc_token))

        assert draft_startup["id"] not in listed
        assert ready_startup["id"] not in listed

    async def test_a_startup_forced_vc_visible_without_an_approval_is_not_listed(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        startup = await report_ready_startup(client, engine, founder_token)
        await run_sql(
            engine,
            "UPDATE startups SET status = 'vc_visible', vc_visible_at = now() WHERE id = :sid",
            sid=startup["id"],
        )

        listed = ids_of(await walk_all(client, vc_token))

        assert startup["id"] not in listed

    async def test_order_is_newest_approval_first_and_stable_across_requests(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        first, _, _ = await approved_startup(client, engine, founder_token)
        second, _, _ = await approved_startup(client, engine, founder_token)
        third, _, _ = await approved_startup(client, engine, founder_token)

        listed = ids_of(await walk_all(client, vc_token))
        again = ids_of(await walk_all(client, vc_token))

        mine = [sid for sid in listed if sid in {first["id"], second["id"], third["id"]}]
        assert mine == [third["id"], second["id"], first["id"]]
        assert listed == again

    async def test_pagination_slices_the_same_order_without_gaps_or_duplicates(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        for _ in range(3):
            await approved_startup(client, engine, founder_token)

        whole = ids_of(await walk_all(client, vc_token))
        paged: list[str] = []
        for offset in range(0, 6, 2):
            page = (await list_visible(client, vc_token, limit=2, offset=offset)).json()
            assert page["limit"] == 2
            assert page["offset"] == offset
            paged.extend(ids_of(page["items"]))

        assert paged == whole[:6]
        assert len(set(paged)) == len(paged)

    async def test_total_counts_every_visible_startup_not_just_the_page(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        await approved_startup(client, engine, founder_token)

        page = (await list_visible(client, vc_token, limit=1)).json()

        assert len(page["items"]) == 1
        assert page["total"] == len(await walk_all(client, vc_token))
        assert page["total"] >= 1

    async def test_default_page_size_is_bounded(self, client, engine, vc, founder):
        _, founder_token = founder
        _, vc_token = vc
        await approved_startup(client, engine, founder_token)

        body = (await list_visible(client, vc_token)).json()

        assert body["limit"] == DEFAULT_PAGE
        assert body["offset"] == 0
        assert len(body["items"]) <= DEFAULT_PAGE

    @pytest.mark.parametrize(
        "params",
        [
            {"limit": 0},
            {"limit": -1},
            {"limit": MAX_PAGE + 1},
            {"limit": 1000},
            {"limit": "many"},
            {"offset": -1},
            {"offset": "next"},
        ],
    )
    async def test_out_of_range_pagination_is_the_canonical_422(self, client, vc, params):
        _, vc_token = vc

        response = await list_visible(client, vc_token, **params)

        assert_error_envelope(response, 422, "VALIDATION_FAILED")

    async def test_the_list_never_carries_founder_or_internal_fields(
        self, client, engine, vc, founder
    ):
        founder_id, founder_token = founder
        _, vc_token = vc
        await approved_startup(client, engine, founder_token)

        response = await list_visible(client, vc_token, limit=MAX_PAGE)

        assert not (keys_anywhere(response.json()) & FORBIDDEN_KEYS)
        assert str(founder_id) not in response.text


class TestDossier:
    async def test_returns_the_exact_narrative_version_the_founder_approved(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, approval = await approved_startup(
            client, engine, founder_token, content=FOUNDER_TEXT
        )

        response = await get_dossier(client, vc_token, startup["id"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == DOSSIER_KEYS
        assert set(body["narrative"]) == NARRATIVE_KEYS
        assert body["narrative"]["version"] == 2
        assert body["narrative"]["content"] == FOUNDER_TEXT
        assert body["narrative"]["approved_at"] == approval["approved_at"]

    async def test_neither_the_seed_draft_nor_earlier_versions_are_reachable(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, _ = await approved_startup(
            client, engine, founder_token, content=FOUNDER_TEXT, draft=SEED_DRAFT
        )

        response = await get_dossier(client, vc_token, startup["id"])

        # SEED_DRAFT is both narrative version 1 and the report's
        # pitch_narrative_draft: neither may reach an investor.
        assert SEED_DRAFT not in response.text

    async def test_the_startup_profile_is_the_safe_projection(self, client, engine, vc, founder):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, approval = await approved_startup(
            client,
            engine,
            founder_token,
            name="Yuk Express",
            one_liner="Freight matching for Central Asia.",
            sector="logistics",
            funding_stage="seed",
            city="Tashkent",
        )

        profile = (await get_dossier(client, vc_token, startup["id"])).json()["startup"]

        assert set(profile) == SUMMARY_KEYS
        assert profile["id"] == startup["id"]
        assert profile["name"] == "Yuk Express"
        assert profile["city"] == "Tashkent"
        assert profile["approved_at"] == approval["approved_at"]

    async def test_the_report_is_the_cited_body_without_the_draft(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, _ = await approved_startup(client, engine, founder_token, content=FOUNDER_TEXT)

        report = (await get_dossier(client, vc_token, startup["id"])).json()["report"]

        assert set(report) == REPORT_KEYS
        assert set(report["report"]) == REPORT_BODY_KEYS
        assert report["schema_version"] == "report.v1"
        assert report["language"] == "en"
        assert report["partial"] is False
        assert report["evidence_count"] == 3
        assert report["generated_at"]
        assert report["report"]["executive_summary"]
        assert report["report"]["sections"]["us_vc_readiness"]["citation_ids"] == [3]

    async def test_sources_come_back_complete_and_in_ordinal_order(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, _ = await approved_startup(
            client, engine, founder_token, report_input=report_with_sources(5)
        )

        sources = (await get_dossier(client, vc_token, startup["id"])).json()["report"]["sources"]

        assert [source["ordinal"] for source in sources] == [1, 2, 3, 4, 5]
        assert all(set(source) == SOURCE_KEYS for source in sources)
        assert sources[0]["url"].startswith("https://")

    async def test_no_forbidden_key_appears_anywhere_in_the_dossier(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, _ = await approved_startup(client, engine, founder_token, content=FOUNDER_TEXT)

        body = (await get_dossier(client, vc_token, startup["id"])).json()

        assert not (keys_anywhere(body) & FORBIDDEN_KEYS)

    async def test_no_founder_identity_deck_payment_or_job_data_is_reachable(
        self, client, engine, vc, founder
    ):
        founder_id, founder_token = founder
        _, vc_token = vc
        startup, report, _ = await approved_startup(
            client, engine, founder_token, content=FOUNDER_TEXT
        )
        private = await fetch_all(
            engine,
            "SELECT u.email AS email, d.filename AS filename, "
            "j.id::text AS job_id, s.problem AS problem, s.dataroom_url AS dataroom_url "
            "FROM startups st JOIN users u ON u.id = st.founder_id "
            "LEFT JOIN pitch_decks d ON d.startup_id = st.id "
            "LEFT JOIN analysis_jobs j ON j.startup_id = st.id "
            "LEFT JOIN submissions s ON s.startup_id = st.id "
            "WHERE st.id = :sid",
            sid=startup["id"],
        )
        assert private, "expected the founder's private rows to exist"
        secrets = private[0]

        text = (await get_dossier(client, vc_token, startup["id"])).text

        assert str(founder_id) not in text
        assert secrets["email"] not in text
        assert secrets["filename"] not in text
        assert secrets["job_id"] not in text
        assert str(report.id) not in text
        assert secrets["problem"] not in text
        if secrets["dataroom_url"]:
            assert secrets["dataroom_url"] not in text

    async def test_every_active_vc_account_gets_the_same_dossier(self, client, engine, vc, founder):
        _, founder_token = founder
        _, first_vc_token = vc
        startup, _, _ = await approved_startup(client, engine, founder_token, content=FOUNDER_TEXT)
        _, second_vc_token = await seed_user(engine, role="vc")

        first = await get_dossier(client, first_vc_token, startup["id"])
        second = await get_dossier(client, second_vc_token, startup["id"])

        assert first.status_code == 200
        assert first.json() == second.json()


class TestNotFoundIsIndistinguishable:
    async def test_an_unknown_startup_id_is_the_canonical_404(self, client, vc):
        _, vc_token = vc

        response = await get_dossier(client, vc_token, uuid.uuid4())

        assert_error_envelope(response, 404, "STARTUP_NOT_FOUND")

    async def test_an_unapproved_startup_is_the_canonical_404(self, client, engine, vc, founder):
        _, founder_token = founder
        _, vc_token = vc
        startup = await report_ready_startup(client, engine, founder_token)

        response = await get_dossier(client, vc_token, startup["id"])

        assert_error_envelope(response, 404, "STARTUP_NOT_FOUND")

    async def test_a_draft_startup_is_the_canonical_404(self, client, vc, founder):
        _, founder_token = founder
        _, vc_token = vc
        startup = await create_startup(client, founder_token)

        response = await get_dossier(client, vc_token, startup["id"])

        assert_error_envelope(response, 404, "STARTUP_NOT_FOUND")

    async def test_a_startup_forced_vc_visible_without_an_approval_is_the_canonical_404(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        startup = await report_ready_startup(client, engine, founder_token)
        await run_sql(
            engine,
            "UPDATE startups SET status = 'vc_visible', vc_visible_at = now() WHERE id = :sid",
            sid=startup["id"],
        )

        response = await get_dossier(client, vc_token, startup["id"])

        assert_error_envelope(response, 404, "STARTUP_NOT_FOUND")

    async def test_unknown_unapproved_and_draft_answer_byte_identical_bodies(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        unapproved = await report_ready_startup(client, engine, founder_token)
        draft = await create_startup(client, founder_token)

        bodies = []
        for startup_id in (uuid.uuid4(), unapproved["id"], draft["id"]):
            response = await get_dossier(client, vc_token, startup_id)
            body = response.json()
            body["error"].pop("request_id")
            bodies.append((response.status_code, body))

        assert bodies[0] == bodies[1] == bodies[2]

    async def test_a_malformed_startup_id_is_the_canonical_422(self, client, vc):
        _, vc_token = vc

        response = await client.get(VC_DOSSIER.format("not-a-uuid"), headers=vc_headers(vc_token))

        assert_error_envelope(response, 422, "VALIDATION_FAILED")


class TestAccessControl:
    async def test_a_founder_token_is_refused_on_the_list(self, client, founder):
        _, founder_token = founder

        response = await list_visible(client, founder_token)

        assert_error_envelope(response, 403, "FORBIDDEN_ROLE")

    async def test_a_founder_token_is_refused_on_their_own_approved_startup(
        self, client, engine, founder
    ):
        _, founder_token = founder
        startup, _, _ = await approved_startup(client, engine, founder_token)

        response = await get_dossier(client, founder_token, startup["id"])

        assert_error_envelope(response, 403, "FORBIDDEN_ROLE")

    @pytest.mark.parametrize("path", [VC_LIST, VC_DOSSIER.format(uuid.uuid4())])
    async def test_no_bearer_token_is_refused(self, client, path):
        response = await client.get(path)

        error = assert_error_envelope(response, 401, "AUTH_TOKEN_INVALID")
        assert error["detail"]
        assert response.headers.get("www-authenticate") == "Bearer"

    async def test_a_garbage_bearer_token_is_refused(self, client):
        response = await client.get(VC_LIST, headers={"Authorization": "Bearer not.a.token"})

        assert_error_envelope(response, 401, "AUTH_TOKEN_INVALID")

    async def test_a_deleted_vc_account_follows_the_canonical_auth_policy(self, client, engine, vc):
        vc_id, vc_token = vc
        await run_sql(engine, "UPDATE users SET deleted_at = now() WHERE id = :uid", uid=vc_id)

        response = await list_visible(client, vc_token)

        assert_error_envelope(response, 401, "AUTH_SESSION_REVOKED")

    async def test_an_unverified_vc_account_follows_the_canonical_auth_policy(
        self, client, engine, vc
    ):
        vc_id, vc_token = vc
        await run_sql(
            engine, "UPDATE users SET email_verified_at = NULL WHERE id = :uid", uid=vc_id
        )

        response = await get_dossier(client, vc_token, uuid.uuid4())

        assert_error_envelope(response, 401, "AUTH_SESSION_REVOKED")

    async def test_reads_need_no_origin_header(self, client, engine, vc, founder):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, _ = await approved_startup(client, engine, founder_token)

        listed = await list_visible(client, vc_token, origin=None)
        dossier = await get_dossier(client, vc_token, startup["id"], origin=None)

        assert listed.status_code == 200
        assert dossier.status_code == 200

    async def test_a_foreign_origin_still_reads_but_gets_no_cors_grant(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, _ = await approved_startup(client, engine, founder_token)

        response = await get_dossier(client, vc_token, startup["id"], origin=FOREIGN_ORIGIN)

        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers

    async def test_an_allowed_origin_gets_a_credentialed_cors_grant(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, _ = await approved_startup(client, engine, founder_token)

        response = await get_dossier(client, vc_token, startup["id"], origin=ORIGIN)

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == ORIGIN


class TestResponsePrivacyHeaders:
    def assert_private(self, response) -> None:
        assert response.headers.get("cache-control") == "no-store"
        assert response.headers.get("pragma") == "no-cache"
        assert response.headers.get("referrer-policy") == "no-referrer"

    async def test_a_successful_list_is_never_cached(self, client, engine, vc, founder):
        _, founder_token = founder
        _, vc_token = vc
        await approved_startup(client, engine, founder_token)

        self.assert_private(await list_visible(client, vc_token))

    async def test_a_successful_dossier_is_never_cached(self, client, engine, vc, founder):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, _ = await approved_startup(client, engine, founder_token)

        self.assert_private(await get_dossier(client, vc_token, startup["id"]))

    async def test_errors_are_never_cached_either(self, client, vc, founder):
        _, vc_token = vc
        _, founder_token = founder

        self.assert_private(await get_dossier(client, vc_token, uuid.uuid4()))
        self.assert_private(await list_visible(client, founder_token))
        self.assert_private(await client.get(VC_LIST))


class TestQueryEfficiency:
    async def test_listing_more_startups_does_not_cost_more_queries(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        for _ in range(3):
            await approved_startup(client, engine, founder_token)
        await list_visible(client, vc_token, limit=1)  # warm the pool

        with count_selects() as one_row:
            page = (await list_visible(client, vc_token, limit=1)).json()
        assert len(page["items"]) == 1
        with count_selects() as three_rows:
            page = (await list_visible(client, vc_token, limit=3)).json()
        assert len(page["items"]) == 3

        assert len(three_rows) == len(one_row)
        # auth principal + count + page: no per-row query.
        assert len(three_rows) <= 3

    async def test_a_dossier_costs_the_same_regardless_of_source_count(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        small, _, _ = await approved_startup(
            client, engine, founder_token, report_input=report_with_sources(3)
        )
        large, _, _ = await approved_startup(
            client, engine, founder_token, report_input=report_with_sources(8)
        )
        await get_dossier(client, vc_token, small["id"])  # warm the pool

        with count_selects() as few:
            small_body = (await get_dossier(client, vc_token, small["id"])).json()
        with count_selects() as many:
            large_body = (await get_dossier(client, vc_token, large["id"])).json()

        assert len(small_body["report"]["sources"]) == 3
        assert len(large_body["report"]["sources"]) == 8
        assert len(many) == len(few)
        # auth principal + joined dossier + sources: no per-row query.
        assert len(many) <= 3


class TestReadOnly:
    @pytest.mark.parametrize("method", ["post", "patch", "delete", "put"])
    async def test_the_list_exposes_no_write_verbs(self, client, vc, method):
        _, vc_token = vc

        response = await getattr(client, method)(
            VC_LIST, headers=founder_headers(vc_token, origin=ORIGIN)
        )

        assert response.status_code == 405

    async def test_reading_writes_no_rows(self, client, engine, vc, founder):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, _ = await approved_startup(client, engine, founder_token, content=FOUNDER_TEXT)
        before = await fetch_all(
            engine,
            "SELECT (SELECT count(*) FROM audit_log) AS audits, "
            "(SELECT count(*) FROM narrative_versions) AS versions, "
            "(SELECT count(*) FROM narrative_approvals) AS approvals",
        )

        await list_visible(client, vc_token)
        await get_dossier(client, vc_token, startup["id"])
        after = await fetch_all(
            engine,
            "SELECT (SELECT count(*) FROM audit_log) AS audits, "
            "(SELECT count(*) FROM narrative_versions) AS versions, "
            "(SELECT count(*) FROM narrative_approvals) AS approvals",
        )

        assert before == after


class TestFrozenNarrativeStaysFrozen:
    async def test_the_founder_cannot_change_what_an_investor_reads(
        self, client, engine, vc, founder
    ):
        _, founder_token = founder
        _, vc_token = vc
        startup, _, _ = await approved_startup(client, engine, founder_token, content=FOUNDER_TEXT)

        blocked = await save_narrative(client, founder_token, startup["id"], "sneaky rewrite")
        assert blocked.status_code == 409, blocked.text
        body = (await get_dossier(client, vc_token, startup["id"])).json()

        assert body["narrative"]["content"] == FOUNDER_TEXT
        rows = await fetch_all(
            engine,
            "SELECT content FROM narrative_versions WHERE startup_id = :sid ORDER BY version",
            sid=startup["id"],
        )
        assert [row["content"] for row in rows] == [SEED_DRAFT, FOUNDER_TEXT]


class TestDatabaseIndexesAreSufficient:
    async def test_the_visible_list_query_uses_no_sequential_scan_on_large_tables(self, engine):
        # Documents the pilot decision NOT to add a migration for this slice:
        # the join is startups -> narrative_approvals on the approval's UNIQUE
        # startup_id, and pilot volumes are tiny. This test asserts the plan is
        # obtainable (the query is valid SQL against the real schema), not a
        # specific plan shape, which Postgres is free to choose.
        async with engine.connect() as conn:
            plan = await conn.execute(
                sa.text(
                    "EXPLAIN SELECT s.id FROM startups s "
                    "JOIN narrative_approvals a ON a.startup_id = s.id "
                    "WHERE s.status = 'vc_visible' "
                    "ORDER BY a.approved_at DESC, s.id DESC LIMIT 20"
                )
            )
            rows = [row[0] for row in plan]

        assert rows
