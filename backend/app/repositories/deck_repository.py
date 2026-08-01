"""PostgreSQL implementation of the DeckStorage protocol (BYTEA-backed).

Every statement projects explicit columns. `content` appears ONLY in put()
(which by definition writes it) and get_content() (the authorized download);
metadata reads and deletes never mention the column, so the private bytes
cannot cross the wire for list/hydration-style queries even by accident.
"""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PitchDeck
from app.models.pitch_deck import DECK_MIME_TYPE
from app.services.deck_storage import DeckMetadata
from app.services.pdf_validation import DeckFile

_DECKS = PitchDeck.__table__

_METADATA_COLUMNS = (
    _DECKS.c.id,
    _DECKS.c.startup_id,
    _DECKS.c.filename,
    _DECKS.c.mime_type,
    _DECKS.c.size_bytes,
    _DECKS.c.sha256,
    _DECKS.c.page_count,
    _DECKS.c.uploaded_at,
)


def _metadata(row: Row) -> DeckMetadata:
    return DeckMetadata(
        id=row.id,
        startup_id=row.startup_id,
        filename=row.filename,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        sha256=bytes(row.sha256),
        page_count=row.page_count,
        uploaded_at=row.uploaded_at,
    )


class PostgresDeckStorage:
    """DeckStorage over the pitch_decks table; flushes, never commits."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_metadata(self, startup_id: uuid.UUID) -> DeckMetadata | None:
        stmt = select(*_METADATA_COLUMNS).where(_DECKS.c.startup_id == startup_id)
        row = (await self._session.execute(stmt)).one_or_none()
        return _metadata(row) if row is not None else None

    async def get_content(self, startup_id: uuid.UUID) -> tuple[DeckMetadata, bytes] | None:
        stmt = select(*_METADATA_COLUMNS, _DECKS.c.content).where(_DECKS.c.startup_id == startup_id)
        row = (await self._session.execute(stmt)).one_or_none()
        return (_metadata(row), bytes(row.content)) if row is not None else None

    async def put(self, startup_id: uuid.UUID, deck: DeckFile, content: bytes) -> DeckMetadata:
        values = {
            "startup_id": startup_id,
            "filename": deck.filename,
            "mime_type": DECK_MIME_TYPE,
            "size_bytes": deck.size_bytes,
            "sha256": deck.sha256,
            "page_count": deck.page_count,
            "content": content,
        }
        stmt = pg_insert(_DECKS).values(values)
        # One deck per startup: a second upload rewrites the existing row in
        # place (same id) and restamps uploaded_at, atomically.
        stmt = stmt.on_conflict_do_update(
            constraint="uq_pitch_decks_startup_id",
            set_={
                **{k: stmt.excluded[k] for k in values if k != "startup_id"},
                "uploaded_at": func.now(),
            },
        ).returning(*_METADATA_COLUMNS)
        row = (await self._session.execute(stmt)).one()
        return _metadata(row)

    async def delete(self, startup_id: uuid.UUID) -> bool:
        stmt = delete(_DECKS).where(_DECKS.c.startup_id == startup_id)
        result = await self._session.execute(stmt)
        return bool(result.rowcount)
