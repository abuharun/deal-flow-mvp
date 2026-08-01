"""PostgresDeckStorage against real Postgres.

Contracts under test:
- put() is an atomic upsert: first call inserts, second call for the same
  startup replaces every stored field in place (still exactly one row, same
  primary key) and refreshes uploaded_at.
- get_metadata()/delete() never touch the content column at the SQL level —
  proven by capturing every emitted statement — so a later object-storage
  backend can implement the same protocol without a BYTEA in sight.
- get_content() returns the exact stored bytes for the download path only.
- The metadata value object physically has no content field to leak.
"""

import dataclasses
import hashlib
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from app.db import build_engine, build_sessionmaker
from app.repositories.deck_repository import PostgresDeckStorage
from app.services.deck_storage import DeckMetadata
from app.services.pdf_validation import DeckFile


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
def captured_sql(engine):
    statements: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    yield statements
    event.remove(engine.sync_engine, "before_cursor_execute", capture)


async def seed_startup(engine) -> uuid.UUID:
    async with build_sessionmaker(engine)() as session:
        founder_id = (
            await session.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role, "
                    "email_verified_at) VALUES (:email, 'x', 'Deck Owner', 'founder', now()) "
                    "RETURNING id"
                ),
                {"email": f"deckstore-{uuid.uuid4().hex}@example.com"},
            )
        ).scalar_one()
        startup_id = (
            await session.execute(
                sa.text(
                    "INSERT INTO startups (founder_id, name) "
                    "VALUES (:founder_id, 'Deck Startup') RETURNING id"
                ),
                {"founder_id": str(founder_id)},
            )
        ).scalar_one()
        await session.commit()
    return startup_id


def deck_file(content: bytes, filename: str = "deck.pdf", page_count: int = 1) -> DeckFile:
    return DeckFile(
        filename=filename,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).digest(),
        page_count=page_count,
    )


async def fetch_deck_rows(engine, startup_id: uuid.UUID) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text("SELECT * FROM pitch_decks WHERE startup_id = :sid"),
            {"sid": str(startup_id)},
        )
        return [dict(row) for row in result.mappings()]


class TestPut:
    async def test_put_inserts_one_row_and_returns_metadata(self, engine):
        startup_id = await seed_startup(engine)
        content = b"%PDF-1.4 first deck"
        async with build_sessionmaker(engine)() as session:
            metadata = await PostgresDeckStorage(session).put(
                startup_id, deck_file(content), content
            )
            await session.commit()

        assert metadata.startup_id == startup_id
        assert metadata.filename == "deck.pdf"
        assert metadata.mime_type == "application/pdf"
        assert metadata.size_bytes == len(content)
        assert metadata.sha256 == hashlib.sha256(content).digest()
        assert metadata.page_count == 1
        assert metadata.uploaded_at.tzinfo is not None

        rows = await fetch_deck_rows(engine, startup_id)
        assert len(rows) == 1
        assert bytes(rows[0]["content"]) == content

    async def test_put_replaces_the_existing_row_in_place(self, engine):
        startup_id = await seed_startup(engine)
        first_content = b"%PDF-1.4 first deck"
        second_content = b"%PDF-1.7 replacement deck, longer"
        async with build_sessionmaker(engine)() as session:
            storage = PostgresDeckStorage(session)
            first = await storage.put(startup_id, deck_file(first_content), first_content)
            await session.commit()
            second = await storage.put(
                startup_id, deck_file(second_content, "v2.pdf", 2), second_content
            )
            await session.commit()

        assert second.id == first.id, "replacement rewrites the same row"
        assert second.filename == "v2.pdf"
        assert second.page_count == 2
        assert second.uploaded_at >= first.uploaded_at

        rows = await fetch_deck_rows(engine, startup_id)
        assert len(rows) == 1
        assert bytes(rows[0]["content"]) == second_content

    async def test_metadata_value_object_has_no_content_field(self):
        assert "content" not in {f.name for f in dataclasses.fields(DeckMetadata)}


class TestMetadataAndContent:
    async def test_get_metadata_returns_none_when_absent(self, engine):
        startup_id = await seed_startup(engine)
        async with build_sessionmaker(engine)() as session:
            assert await PostgresDeckStorage(session).get_metadata(startup_id) is None

    async def test_get_metadata_never_selects_the_content_column(self, engine, captured_sql):
        startup_id = await seed_startup(engine)
        content = b"%PDF-1.4 private bytes"
        async with build_sessionmaker(engine)() as session:
            storage = PostgresDeckStorage(session)
            await storage.put(startup_id, deck_file(content), content)
            await session.commit()

        captured_sql.clear()
        async with build_sessionmaker(engine)() as session:
            metadata = await PostgresDeckStorage(session).get_metadata(startup_id)
        assert metadata is not None
        assert metadata.size_bytes == len(content)
        assert captured_sql, "expected the metadata SELECT to be captured"
        for statement in captured_sql:
            assert "content" not in statement, statement

    async def test_get_content_returns_the_exact_stored_bytes(self, engine):
        startup_id = await seed_startup(engine)
        content = b"%PDF-1.4 exact bytes \x00\xff"
        async with build_sessionmaker(engine)() as session:
            storage = PostgresDeckStorage(session)
            await storage.put(startup_id, deck_file(content), content)
            await session.commit()
            loaded = await storage.get_content(startup_id)

        assert loaded is not None
        metadata, loaded_bytes = loaded
        assert loaded_bytes == content
        assert metadata.sha256 == hashlib.sha256(content).digest()

    async def test_get_content_returns_none_when_absent(self, engine):
        startup_id = await seed_startup(engine)
        async with build_sessionmaker(engine)() as session:
            assert await PostgresDeckStorage(session).get_content(startup_id) is None


class TestDelete:
    async def test_delete_removes_the_row_and_reports_it(self, engine):
        startup_id = await seed_startup(engine)
        content = b"%PDF-1.4 doomed deck"
        async with build_sessionmaker(engine)() as session:
            storage = PostgresDeckStorage(session)
            await storage.put(startup_id, deck_file(content), content)
            await session.commit()
            assert await storage.delete(startup_id) is True
            await session.commit()

        assert await fetch_deck_rows(engine, startup_id) == []

    async def test_delete_of_absent_deck_reports_false(self, engine):
        startup_id = await seed_startup(engine)
        async with build_sessionmaker(engine)() as session:
            assert await PostgresDeckStorage(session).delete(startup_id) is False

    async def test_delete_never_selects_the_content_column(self, engine, captured_sql):
        startup_id = await seed_startup(engine)
        content = b"%PDF-1.4 private bytes"
        async with build_sessionmaker(engine)() as session:
            storage = PostgresDeckStorage(session)
            await storage.put(startup_id, deck_file(content), content)
            await session.commit()

        captured_sql.clear()
        async with build_sessionmaker(engine)() as session:
            assert await PostgresDeckStorage(session).delete(startup_id) is True
            await session.commit()
        for statement in captured_sql:
            assert "content" not in statement, statement
