"""Founder pitch-deck lifecycle: upload/replace, download, delete.

Transaction contract (same as the other services): every function stages
rows and flushes but never commits — the endpoint owns the boundary, so the
deck row, the input_revision bump, and the audit row commit or roll back
together. A failed validation or a failed write leaves the prior deck (and
the revision) exactly as it was.

Audit hygiene: metadata carries IDs, the SANITIZED filename, byte size,
SHA-256 hex, page count, status, and input_revision — never the original
unsafe filename and never a single content byte.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditActorType, Startup
from app.services.audit_service import write_audit
from app.services.deck_storage import DeckMetadata, DeckStorage
from app.services.deck_upload import UploadedDeck
from app.services.pdf_validation import validate_deck
from app.services.startup_service import StartupLockedError, is_locked


class DeckNotFoundError(Exception):
    """The founder's startup exists but has no pitch deck."""


def ensure_deck_mutable(startup: Startup) -> None:
    """Refuse deck mutations once the startup is VC-visible.

    Routes call this BEFORE consuming the upload body, so a locked startup
    never causes the server to read a single content byte.
    """
    if is_locked(startup):
        raise StartupLockedError


async def _audit(
    session: AsyncSession, startup: Startup, action: str, metadata: DeckMetadata
) -> None:
    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        actor_id=startup.founder_id,
        action=action,
        entity_type="startup",
        entity_id=startup.id,
        metadata={
            "status": startup.status.value,
            "input_revision": startup.input_revision,
            "deck_id": str(metadata.id),
            "deck_filename": metadata.filename,
            "deck_size_bytes": metadata.size_bytes,
            "deck_sha256": metadata.sha256.hex(),
            "deck_page_count": metadata.page_count,
        },
    )


async def upload_deck(
    session: AsyncSession, storage: DeckStorage, *, startup: Startup, upload: UploadedDeck
) -> tuple[DeckMetadata, bool]:
    """Validate and atomically insert/replace the startup's single deck.

    Returns (metadata, created). A deck change is material founder input, so
    input_revision moves forward exactly once per successful call.
    """
    ensure_deck_mutable(startup)
    deck = validate_deck(
        upload.content, filename=upload.filename, declared_mime=upload.declared_mime
    )
    created = await storage.get_metadata(startup.id) is None
    metadata = await storage.put(startup.id, deck, upload.content)
    startup.input_revision += 1
    await session.flush()
    action = "startup.deck_upload" if created else "startup.deck_replace"
    await _audit(session, startup, action, metadata)
    return metadata, created


async def delete_deck(session: AsyncSession, storage: DeckStorage, *, startup: Startup) -> None:
    """Remove the deck; removing founder input is itself a material revision."""
    ensure_deck_mutable(startup)
    existing = await storage.get_metadata(startup.id)
    if existing is None:
        raise DeckNotFoundError
    await storage.delete(startup.id)
    startup.input_revision += 1
    await session.flush()
    await _audit(session, startup, "startup.deck_delete", existing)


async def download_deck(
    session: AsyncSession, storage: DeckStorage, *, startup: Startup
) -> tuple[DeckMetadata, bytes]:
    """The deck's exact bytes for the authorized founder, with an audit row.

    Reads never bump input_revision; the caller commits the audit before the
    bytes leave the app.
    """
    loaded = await storage.get_content(startup.id)
    if loaded is None:
        raise DeckNotFoundError
    metadata, content = loaded
    await _audit(session, startup, "startup.deck_download", metadata)
    return metadata, content


async def get_deck_metadata(storage: DeckStorage, *, startup: Startup) -> DeckMetadata:
    """Metadata view; never touches the content bytes."""
    metadata = await storage.get_metadata(startup.id)
    if metadata is None:
        raise DeckNotFoundError
    return metadata
