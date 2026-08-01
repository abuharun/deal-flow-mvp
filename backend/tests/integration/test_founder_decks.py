"""Founder pitch-deck endpoints (/founder/startups/{id}/deck).

Contracts under test:
- PUT uploads or atomically replaces the startup's single private PDF
  (201 create / 200 replace) and bumps input_revision exactly once per
  successful mutation; any refused upload changes NOTHING — no row, no
  revision, and a prior deck survives byte-for-byte.
- Validation refusals (size, extension, MIME, magic, structure, encryption,
  page count) each answer a canonical error that never echoes the filename,
  MIME string, or any uploaded byte.
- GET streams the exact bytes with safe download headers (nosniff, private
  no-store cache, SHA-256 ETag, RFC 6266 Content-Disposition with an ASCII
  fallback and UTF-8 filename*); GET /metadata never carries content.
- DELETE removes the deck (204) and bumps input_revision; no deck is a
  canonical 404 DECK_NOT_FOUND.
- Once VC-visible (timestamp or status), every mutation answers the
  canonical 409 STARTUP_LOCKED; the founder can still read.
- Foreign and unknown startups share one 404 STARTUP_NOT_FOUND; VC tokens
  get 403 FORBIDDEN_ROLE; PUT/DELETE demand an exact allowed Origin, checked
  before anything else.
- Audit rows carry IDs, sanitized filename, size, SHA-256 hex, and
  input_revision — never bytes or the original unsafe filename.
- Startup list/detail queries never touch the pitch_decks table at all.
"""

import hashlib
import uuid
from io import BytesIO
from urllib.parse import quote

import pytest
import sqlalchemy as sa
from pypdf import PdfWriter
from sqlalchemy import event

from app.db import build_engine, build_sessionmaker
from app.models.pitch_deck import MAX_DECK_BYTES
from tests.integration.test_founder_startups import (
    assert_error_envelope,
    build_app,
    create_startup,
    founder_headers,
    open_client,
    seed_user,
)

DECK = "/founder/startups/{}/deck"


def make_pdf(pages: int = 1, *, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if password is not None:
        writer.encrypt(password)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def pad_pdf(pdf: bytes, target_size: int) -> bytes:
    return pdf + b"\n%" + b"0" * (target_size - len(pdf) - 2)


def pdf_file(content: bytes, filename: str = "deck.pdf", mime: str = "application/pdf"):
    return {"file": (filename, content, mime)}


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


async def get_revision(client, token: str, startup_id: str) -> int:
    response = await client.get(f"/founder/startups/{startup_id}", headers=founder_headers(token))
    assert response.status_code == 200, response.text
    return response.json()["input_revision"]


async def upload(client, token: str, startup_id: str, content: bytes, **file_kwargs):
    return await client.put(
        DECK.format(startup_id),
        files=pdf_file(content, **file_kwargs),
        headers=founder_headers(token),
    )


async def deck_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT id, filename, mime_type, size_bytes, sha256, page_count, content "
        "FROM pitch_decks WHERE startup_id = :sid",
        sid=startup_id,
    )


async def deck_audit_rows(engine, startup_id: str) -> list[dict]:
    return await fetch_all(
        engine,
        "SELECT action, metadata::text AS metadata_text FROM audit_log "
        "WHERE entity_id = :sid AND action LIKE 'startup.deck%' ORDER BY at, id",
        sid=startup_id,
    )


class TestUpload:
    async def test_first_upload_creates_the_deck_and_bumps_revision(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        content = make_pdf(pages=3)

        response = await upload(client, token, startup["id"], content, filename="Seed Deck.pdf")

        assert response.status_code == 201, response.text
        body = response.json()
        assert uuid.UUID(body["id"])
        assert body["filename"] == "Seed Deck.pdf"
        assert body["mime_type"] == "application/pdf"
        assert body["size_bytes"] == len(content)
        assert body["sha256"] == hashlib.sha256(content).hexdigest()
        assert body["page_count"] == 3
        assert body["uploaded_at"]
        assert "content" not in body

        rows = await deck_rows(engine, startup["id"])
        assert len(rows) == 1
        assert bytes(rows[0]["content"]) == content
        assert await get_revision(client, token, startup["id"]) == 2

    async def test_exactly_five_mib_is_accepted(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        content = pad_pdf(make_pdf(), MAX_DECK_BYTES)
        assert len(content) == MAX_DECK_BYTES

        response = await upload(client, token, startup["id"], content)

        assert response.status_code == 201, response.text
        assert response.json()["size_bytes"] == MAX_DECK_BYTES

    async def test_one_byte_over_five_mib_is_refused_without_a_row(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        content = pad_pdf(make_pdf(), MAX_DECK_BYTES + 1)

        response = await upload(client, token, startup["id"], content)

        assert_error_envelope(response, 413, "DECK_TOO_LARGE")
        assert await deck_rows(engine, startup["id"]) == []
        assert await get_revision(client, token, startup["id"]) == 1

    async def test_replacement_returns_200_and_swaps_bytes_atomically(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        first, second = make_pdf(pages=1), make_pdf(pages=2)

        first_response = await upload(client, token, startup["id"], first)
        assert first_response.status_code == 201
        second_response = await upload(client, token, startup["id"], second, filename="v2.pdf")

        assert second_response.status_code == 200, second_response.text
        body = second_response.json()
        assert body["filename"] == "v2.pdf"
        assert body["sha256"] == hashlib.sha256(second).hexdigest()
        rows = await deck_rows(engine, startup["id"])
        assert len(rows) == 1
        assert bytes(rows[0]["content"]) == second
        assert await get_revision(client, token, startup["id"]) == 3

    async def test_upload_is_still_allowed_after_submission(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await run_sql(
            engine,
            "UPDATE startups SET status = 'submitted', submitted_at = now() WHERE id = :id",
            id=startup["id"],
        )
        response = await upload(client, token, startup["id"], make_pdf())
        assert response.status_code == 201, response.text

    @pytest.mark.parametrize(
        ("code", "content", "file_kwargs"),
        [
            ("DECK_EMPTY", b"", {}),
            ("DECK_BAD_EXTENSION", None, {"filename": "deck.txt"}),
            ("DECK_BAD_EXTENSION", None, {"filename": "deck.pdf.exe"}),
            ("DECK_BAD_MIME", None, {"mime": "text/plain"}),
            ("DECK_BAD_MIME", None, {"mime": "application/x-pdf"}),
            ("DECK_INVALID_PDF", b"JUNK%PDF-1.4 not at start", {}),
            ("DECK_INVALID_PDF", b"%PDF-1.4 garbage garbage", {}),
            ("DECK_ENCRYPTED", "encrypted", {}),
            ("DECK_PAGE_COUNT", "zero_pages", {}),
            ("DECK_PAGE_COUNT", "sixteen_pages", {}),
        ],
    )
    async def test_invalid_uploads_are_refused_and_change_nothing(
        self, client, engine, code, content, file_kwargs
    ):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        if content is None:
            content = make_pdf()
        elif content == "encrypted":
            content = make_pdf(password="secret")
        elif content == "zero_pages":
            content = make_pdf(pages=0)
        elif content == "sixteen_pages":
            content = make_pdf(pages=16)

        response = await upload(client, token, startup["id"], content, **file_kwargs)

        assert_error_envelope(response, 422, code)
        assert await deck_rows(engine, startup["id"]) == []
        assert await get_revision(client, token, startup["id"]) == 1
        assert await deck_audit_rows(engine, startup["id"]) == []

    async def test_truncated_pdf_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await upload(client, token, startup["id"], make_pdf()[:100])
        assert_error_envelope(response, 422, "DECK_INVALID_PDF")

    async def test_failed_replacement_keeps_the_prior_deck_and_revision(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        good = make_pdf(pages=2)
        assert (await upload(client, token, startup["id"], good)).status_code == 201

        response = await upload(client, token, startup["id"], make_pdf(password="x"))

        assert_error_envelope(response, 422, "DECK_ENCRYPTED")
        rows = await deck_rows(engine, startup["id"])
        assert len(rows) == 1
        assert bytes(rows[0]["content"]) == good
        assert await get_revision(client, token, startup["id"]) == 2

    async def test_audit_failure_rolls_back_and_keeps_the_prior_deck(
        self, test_database_url, db_at_head, engine, monkeypatch
    ):
        async with open_client(test_database_url, raise_app_exceptions=False) as client:
            _, token = await seed_user(engine)
            startup = await create_startup(client, token)
            good = make_pdf()
            assert (await upload(client, token, startup["id"], good)).status_code == 201

            import app.services.deck_service as deck_service

            async def broken_audit(*args, **kwargs):
                raise RuntimeError("audit backend down")

            monkeypatch.setattr(deck_service, "write_audit", broken_audit)
            response = await upload(client, token, startup["id"], make_pdf(pages=2))

            assert_error_envelope(response, 500, "SERVER_ERROR")
            rows = await deck_rows(engine, startup["id"])
            assert len(rows) == 1
            assert bytes(rows[0]["content"]) == good
            monkeypatch.undo()
            assert await get_revision(client, token, startup["id"]) == 2

    async def test_non_multipart_body_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await client.put(
            DECK.format(startup["id"]), json={"file": "x"}, headers=founder_headers(token)
        )
        assert_error_envelope(response, 415, "UPLOAD_NOT_MULTIPART")

    async def test_multipart_without_a_file_field_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await client.put(
            DECK.format(startup["id"]),
            files={"attachment": ("deck.pdf", make_pdf(), "application/pdf")},
            headers=founder_headers(token),
        )
        assert_error_envelope(response, 422, "UPLOAD_FILE_MISSING")

    async def test_refusals_never_echo_the_hostile_filename(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        hostile = "..\\..\\secret-passwd-file.txt"

        response = await upload(client, token, startup["id"], make_pdf(), filename=hostile)

        assert_error_envelope(response, 422, "DECK_BAD_EXTENSION")
        assert "secret-passwd-file" not in response.text


class TestDownloadAndMetadata:
    async def test_download_returns_exact_bytes_with_safe_headers(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        content = make_pdf(pages=2)
        await upload(client, token, startup["id"], content, filename="Seed Deck.pdf")

        response = await client.get(DECK.format(startup["id"]), headers=founder_headers(token))

        assert response.status_code == 200
        assert response.content == content
        assert response.headers["content-type"] == "application/pdf"
        assert int(response.headers["content-length"]) == len(content)
        assert response.headers["etag"] == f'"{hashlib.sha256(content).hexdigest()}"'
        assert response.headers["x-content-type-options"] == "nosniff"
        cache_control = response.headers["cache-control"]
        assert "private" in cache_control and "no-store" in cache_control
        disposition = response.headers["content-disposition"]
        assert disposition.startswith("attachment;")
        assert 'filename="Seed Deck.pdf"' in disposition
        assert "filename*=UTF-8''Seed%20Deck.pdf" in disposition

    async def test_unicode_filename_gets_ascii_fallback_and_utf8_star_form(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await upload(client, token, startup["id"], make_pdf(), filename="старт презентация.pdf")

        response = await client.get(DECK.format(startup["id"]), headers=founder_headers(token))

        disposition = response.headers["content-disposition"]
        assert disposition.isascii(), "headers must never carry raw non-ASCII"
        assert "\r" not in disposition and "\n" not in disposition
        assert f"filename*=UTF-8''{quote('старт презентация.pdf', safe='')}" in disposition

    async def test_hostile_filename_is_stored_and_served_sanitized(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await upload(client, token, startup["id"], make_pdf(), filename="..\\..\\deck‮.pdf")

        metadata = await client.get(
            DECK.format(startup["id"]) + "/metadata", headers=founder_headers(token)
        )
        assert metadata.status_code == 200
        assert metadata.json()["filename"] == "deck.pdf"

        response = await client.get(DECK.format(startup["id"]), headers=founder_headers(token))
        assert 'filename="deck.pdf"' in response.headers["content-disposition"]

    async def test_metadata_reports_the_deck_without_content(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        content = make_pdf()
        await upload(client, token, startup["id"], content)

        response = await client.get(
            DECK.format(startup["id"]) + "/metadata", headers=founder_headers(token)
        )

        assert response.status_code == 200
        body = response.json()
        assert body["size_bytes"] == len(content)
        assert body["sha256"] == hashlib.sha256(content).hexdigest()
        assert "content" not in body
        assert "%PDF" not in response.text

    async def test_download_without_a_deck_is_a_canonical_404(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        for path in (DECK.format(startup["id"]), DECK.format(startup["id"]) + "/metadata"):
            response = await client.get(path, headers=founder_headers(token))
            assert_error_envelope(response, 404, "DECK_NOT_FOUND")

    async def test_download_stays_available_when_the_startup_is_locked(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        content = make_pdf()
        await upload(client, token, startup["id"], content)
        await run_sql(
            engine, "UPDATE startups SET vc_visible_at = now() WHERE id = :id", id=startup["id"]
        )
        response = await client.get(DECK.format(startup["id"]), headers=founder_headers(token))
        assert response.status_code == 200
        assert response.content == content


class TestDelete:
    async def test_delete_removes_the_deck_and_bumps_revision(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await upload(client, token, startup["id"], make_pdf())

        response = await client.delete(DECK.format(startup["id"]), headers=founder_headers(token))

        assert response.status_code == 204
        assert response.content == b""
        assert await deck_rows(engine, startup["id"]) == []
        assert await get_revision(client, token, startup["id"]) == 3
        follow_up = await client.get(DECK.format(startup["id"]), headers=founder_headers(token))
        assert_error_envelope(follow_up, 404, "DECK_NOT_FOUND")

    async def test_delete_without_a_deck_is_a_canonical_404(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await client.delete(DECK.format(startup["id"]), headers=founder_headers(token))
        assert_error_envelope(response, 404, "DECK_NOT_FOUND")
        assert await get_revision(client, token, startup["id"]) == 1

    async def test_delete_is_still_allowed_after_submission(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await upload(client, token, startup["id"], make_pdf())
        await run_sql(
            engine,
            "UPDATE startups SET status = 'submitted', submitted_at = now() WHERE id = :id",
            id=startup["id"],
        )
        response = await client.delete(DECK.format(startup["id"]), headers=founder_headers(token))
        assert response.status_code == 204


class TestLockedStartups:
    @pytest.mark.parametrize(
        "lock_sql",
        [
            "UPDATE startups SET vc_visible_at = now() WHERE id = :id",
            "UPDATE startups SET status = 'vc_visible' WHERE id = :id",
        ],
    )
    async def test_mutations_on_a_locked_startup_answer_409(self, client, engine, lock_sql):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        content = make_pdf()
        await upload(client, token, startup["id"], content)
        await run_sql(engine, lock_sql, id=startup["id"])

        put_response = await upload(client, token, startup["id"], make_pdf(pages=2))
        assert_error_envelope(put_response, 409, "STARTUP_LOCKED")
        delete_response = await client.delete(
            DECK.format(startup["id"]), headers=founder_headers(token)
        )
        assert_error_envelope(delete_response, 409, "STARTUP_LOCKED")

        rows = await deck_rows(engine, startup["id"])
        assert len(rows) == 1
        assert bytes(rows[0]["content"]) == content
        revisions = await fetch_all(
            engine, "SELECT input_revision FROM startups WHERE id = :id", id=startup["id"]
        )
        assert revisions[0]["input_revision"] == 2


class TestOwnershipAndRoles:
    async def test_foreign_and_unknown_startups_share_one_404(self, client, engine):
        _, owner_token = await seed_user(engine)
        _, other_token = await seed_user(engine)
        startup = await create_startup(client, owner_token)
        await upload(client, owner_token, startup["id"], make_pdf())

        for startup_id in (startup["id"], str(uuid.uuid4())):
            put_response = await upload(client, other_token, startup_id, make_pdf())
            assert_error_envelope(put_response, 404, "STARTUP_NOT_FOUND")
            get_response = await client.get(
                DECK.format(startup_id), headers=founder_headers(other_token)
            )
            assert_error_envelope(get_response, 404, "STARTUP_NOT_FOUND")
            delete_response = await client.delete(
                DECK.format(startup_id), headers=founder_headers(other_token)
            )
            assert_error_envelope(delete_response, 404, "STARTUP_NOT_FOUND")

    async def test_vc_tokens_are_refused_on_every_route(self, client, engine):
        _, founder_token = await seed_user(engine)
        _, vc_token = await seed_user(engine, role="vc")
        startup = await create_startup(client, founder_token)
        await upload(client, founder_token, startup["id"], make_pdf())

        path = DECK.format(startup["id"])
        headers = founder_headers(vc_token)
        for response in (
            await client.put(path, files=pdf_file(make_pdf()), headers=headers),
            await client.get(path, headers=headers),
            await client.get(path + "/metadata", headers=headers),
            await client.delete(path, headers=headers),
        ):
            assert_error_envelope(response, 403, "FORBIDDEN_ROLE")

    async def test_missing_token_is_refused(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await client.get(DECK.format(startup["id"]))
        assert_error_envelope(response, 401, "AUTH_TOKEN_INVALID")


class TestOriginPolicy:
    @pytest.mark.parametrize("origin", [None, "https://evil.example"])
    async def test_put_and_delete_demand_an_exact_allowed_origin(self, client, engine, origin):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        headers = founder_headers(token, origin=origin)

        put_response = await client.put(
            DECK.format(startup["id"]), files=pdf_file(make_pdf()), headers=headers
        )
        assert_error_envelope(put_response, 403, "FORBIDDEN_ORIGIN")
        delete_response = await client.delete(DECK.format(startup["id"]), headers=headers)
        assert_error_envelope(delete_response, 403, "FORBIDDEN_ORIGIN")

    async def test_origin_is_checked_before_the_body_is_even_considered(self, client, engine):
        # An oversized upload from a bad origin must die at the origin gate
        # (403), never reaching the size check (413).
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        response = await client.put(
            DECK.format(startup["id"]),
            files=pdf_file(pad_pdf(make_pdf(), MAX_DECK_BYTES + 1)),
            headers=founder_headers(token, origin="https://evil.example"),
        )
        assert_error_envelope(response, 403, "FORBIDDEN_ORIGIN")

    async def test_reads_stay_origin_free(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await upload(client, token, startup["id"], make_pdf())
        response = await client.get(
            DECK.format(startup["id"]), headers=founder_headers(token, origin=None)
        )
        assert response.status_code == 200


class TestAuditTrail:
    async def test_upload_replace_delete_and_download_are_audited(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        first, second = make_pdf(pages=1), make_pdf(pages=2)

        await upload(client, token, startup["id"], first, filename="..\\first‮.pdf")
        await upload(client, token, startup["id"], second)
        await client.get(DECK.format(startup["id"]), headers=founder_headers(token))
        await client.delete(DECK.format(startup["id"]), headers=founder_headers(token))

        rows = await deck_audit_rows(engine, startup["id"])
        assert [row["action"] for row in rows] == [
            "startup.deck_upload",
            "startup.deck_replace",
            "startup.deck_download",
            "startup.deck_delete",
        ]
        upload_meta = rows[0]["metadata_text"]
        assert '"deck_sha256": "' + hashlib.sha256(first).hexdigest() + '"' in upload_meta
        assert f'"deck_size_bytes": {len(first)}' in upload_meta
        assert '"deck_filename": "first.pdf"' in upload_meta
        assert '"input_revision": 2' in upload_meta
        # The download audit records the deck but never bumps the revision.
        assert '"input_revision": 3' in rows[2]["metadata_text"]
        assert '"input_revision": 4' in rows[3]["metadata_text"]
        assert await get_revision(client, token, startup["id"]) == 4

    async def test_audit_rows_never_carry_bytes_or_the_unsafe_filename(self, client, engine):
        _, token = await seed_user(engine)
        startup = await create_startup(client, token)
        await upload(client, token, startup["id"], make_pdf(), filename="..\\EVIL-ORIGINAL‮.pdf")
        await client.get(DECK.format(startup["id"]), headers=founder_headers(token))

        rows = await deck_audit_rows(engine, startup["id"])
        assert rows, "expected deck audit rows"
        for row in rows:
            assert "%PDF" not in row["metadata_text"]
            assert "EVIL-ORIGINAL‮" not in row["metadata_text"]
            assert "\\u202e" not in row["metadata_text"]


class TestStartupPathsNeverTouchDeckBytes:
    async def test_startup_list_and_detail_never_query_pitch_decks(
        self, test_database_url, db_at_head, engine
    ):
        import httpx

        app = build_app(test_database_url)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                _, token = await seed_user(engine)
                startup = await create_startup(client, token)
                await upload(client, token, startup["id"], make_pdf())

                statements: list[str] = []
                app_engine = app.state.engine

                @event.listens_for(app_engine.sync_engine, "before_cursor_execute")
                def capture(conn, cursor, statement, parameters, context, executemany):
                    statements.append(statement)

                try:
                    listing = await client.get("/founder/startups", headers=founder_headers(token))
                    assert listing.status_code == 200
                    detail = await client.get(
                        f"/founder/startups/{startup['id']}", headers=founder_headers(token)
                    )
                    assert detail.status_code == 200
                finally:
                    event.remove(app_engine.sync_engine, "before_cursor_execute", capture)

        assert statements, "expected captured SQL for the startup reads"
        for statement in statements:
            assert "pitch_decks" not in statement, statement
        assert "%PDF" not in listing.text + detail.text
