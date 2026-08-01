"""Pitch-deck metadata responses.

There is deliberately NO field that could carry the PDF bytes: the metadata
schema is built from DeckMetadata (which has no content either), and the
SHA-256 travels as lowercase hex.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.services.deck_storage import DeckMetadata


class DeckResponse(BaseModel):
    id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    page_count: int
    uploaded_at: datetime

    @classmethod
    def from_metadata(cls, metadata: DeckMetadata) -> "DeckResponse":
        return cls(
            id=metadata.id,
            filename=metadata.filename,
            mime_type=metadata.mime_type,
            size_bytes=metadata.size_bytes,
            sha256=metadata.sha256.hex(),
            page_count=metadata.page_count,
            uploaded_at=metadata.uploaded_at,
        )
