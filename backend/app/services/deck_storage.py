"""Storage seam for pitch-deck bytes.

Routes and services depend on this protocol only, so moving the private PDF
bytes from Postgres BYTEA to object storage later means writing one new
implementation — no route, service, or response shape changes.

DeckMetadata deliberately has NO content field: whatever a caller does with
a metadata value (log it, audit it, serialize it), the private bytes cannot
tag along. Content travels only through get_content/put, in the clear, for
the authorized paths that genuinely need it.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.services.pdf_validation import DeckFile


@dataclass(frozen=True, slots=True)
class DeckMetadata:
    id: uuid.UUID
    startup_id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    sha256: bytes
    page_count: int
    uploaded_at: datetime


class DeckStorage(Protocol):
    async def get_metadata(self, startup_id: uuid.UUID) -> DeckMetadata | None:
        """The startup's deck metadata, without ever reading the bytes."""
        ...

    async def get_content(self, startup_id: uuid.UUID) -> tuple[DeckMetadata, bytes] | None:
        """Metadata plus exact stored bytes — the download path only."""
        ...

    async def put(self, startup_id: uuid.UUID, deck: DeckFile, content: bytes) -> DeckMetadata:
        """Atomic upsert: insert the startup's deck or replace it in place."""
        ...

    async def delete(self, startup_id: uuid.UUID) -> bool:
        """Remove the startup's deck; False if there was none."""
        ...
