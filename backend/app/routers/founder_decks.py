"""Founder-only pitch-deck endpoints (/founder/startups/{startup_id}/deck).

Access model mirrors the startup routes: founder bearer principal (VC gets
the canonical 403), founder-scoped SQL lookups (foreign == unknown == one
canonical 404), and an exact allowed Origin on every state change — checked
as a route dependency, i.e. before a single body byte is read.

Upload path: ownership and the VC-visibility lock are verified BEFORE the
multipart stream is consumed, then the raw stream is read under a hard
5 MiB cap that never trusts Content-Length. Validation errors map onto
fixed canonical envelopes that echo no filename, MIME string, or byte.
"""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from app.deps import SessionDep
from app.errors import ApiError
from app.repositories.deck_repository import PostgresDeckStorage
from app.routers.founder_startups import (
    _STATE_CHANGING,
    FounderPrincipal,
    _load_owned_startup,
    _startup_locked_error,
)
from app.schemas.deck import DeckResponse
from app.services import deck_service
from app.services.deck_service import DeckNotFoundError
from app.services.deck_upload import DeckUploadError, read_deck_upload
from app.services.pdf_validation import DeckValidationError
from app.services.startup_service import StartupLockedError

router = APIRouter(prefix="/founder/startups/{startup_id}/deck", tags=["founder-decks"])

_TOO_LARGE = (413, "DECK_TOO_LARGE", "errors.deckTooLarge", "pdf may be at most 5 MiB")

# Fixed catalogue: every refusal answers one of these envelopes, so no
# user-controlled value (filename, MIME, bytes) can ever reach a response.
_VALIDATION_ERRORS: dict[str, tuple[int, str, str, str]] = {
    "empty": (422, "DECK_EMPTY", "errors.deckEmpty", "uploaded file is empty"),
    "too_large": _TOO_LARGE,
    "bad_extension": (
        422,
        "DECK_BAD_EXTENSION",
        "errors.deckBadExtension",
        "filename must end in .pdf",
    ),
    "bad_mime": (
        422,
        "DECK_BAD_MIME",
        "errors.deckBadMime",
        "file must be uploaded as application/pdf",
    ),
    "not_pdf": (422, "DECK_INVALID_PDF", "errors.deckInvalidPdf", "file is not a valid PDF"),
    "malformed": (422, "DECK_INVALID_PDF", "errors.deckInvalidPdf", "file is not a valid PDF"),
    "encrypted": (
        422,
        "DECK_ENCRYPTED",
        "errors.deckEncrypted",
        "encrypted PDFs are not accepted",
    ),
    "page_count": (
        422,
        "DECK_PAGE_COUNT",
        "errors.deckPageCount",
        "pdf must have between 1 and 15 pages",
    ),
}

_UPLOAD_ERRORS: dict[str, tuple[int, str, str, str]] = {
    "not_multipart": (
        415,
        "UPLOAD_NOT_MULTIPART",
        "errors.uploadNotMultipart",
        "request body must be multipart/form-data",
    ),
    "missing_file": (
        422,
        "UPLOAD_FILE_MISSING",
        "errors.uploadFileMissing",
        "multipart field 'file' is required",
    ),
    "too_large": _TOO_LARGE,
    "malformed": (
        422,
        "UPLOAD_MALFORMED",
        "errors.uploadMalformed",
        "multipart body could not be parsed",
    ),
}


def _catalogue_error(catalogue: dict[str, tuple[int, str, str, str]], reason: str) -> ApiError:
    return ApiError(*catalogue[reason])


def _deck_not_found() -> ApiError:
    # Only the verified owner ever sees this; everyone else already got the
    # canonical STARTUP_NOT_FOUND, so deck existence cannot leak ownership.
    return ApiError(404, "DECK_NOT_FOUND", "errors.deckNotFound", "no pitch deck uploaded")


def _content_disposition(filename: str) -> str:
    """RFC 6266 header from a SANITIZED filename (no controls, quotes, CR/LF).

    ASCII fallback for legacy agents plus the RFC 5987 UTF-8 filename* form;
    percent-encoding leaves nothing capable of header injection.
    """
    fallback = filename.encode("ascii", "replace").decode("ascii")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


@router.put("", **_STATE_CHANGING)
async def upload_deck(
    startup_id: UUID,
    request: Request,
    response: Response,
    principal: FounderPrincipal,
    session: SessionDep,
) -> DeckResponse:
    try:
        # FOR UPDATE serializes concurrent deck mutations of one startup so
        # input_revision moves forward by exactly one per transaction.
        startup = await _load_owned_startup(session, startup_id, principal, for_update=True)
        deck_service.ensure_deck_mutable(startup)
        upload = await read_deck_upload(
            request.stream(), content_type=request.headers.get("content-type")
        )
        metadata, created = await deck_service.upload_deck(
            session, PostgresDeckStorage(session), startup=startup, upload=upload
        )
        await session.commit()
    except StartupLockedError:
        await session.rollback()
        raise _startup_locked_error() from None
    except DeckUploadError as exc:
        await session.rollback()
        raise _catalogue_error(_UPLOAD_ERRORS, exc.reason) from None
    except DeckValidationError as exc:
        await session.rollback()
        raise _catalogue_error(_VALIDATION_ERRORS, exc.reason) from None
    except Exception:
        await session.rollback()
        raise
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return DeckResponse.from_metadata(metadata)


@router.get("")
async def download_deck(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> Response:
    try:
        startup = await _load_owned_startup(session, startup_id, principal)
        metadata, content = await deck_service.download_deck(
            session, PostgresDeckStorage(session), startup=startup
        )
        # The download audit row commits BEFORE any byte leaves the app.
        await session.commit()
    except DeckNotFoundError:
        await session.rollback()
        raise _deck_not_found() from None
    except Exception:
        await session.rollback()
        raise
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "ETag": f'"{metadata.sha256.hex()}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Disposition": _content_disposition(metadata.filename),
        },
    )


@router.get("/metadata")
async def get_deck_metadata(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> DeckResponse:
    startup = await _load_owned_startup(session, startup_id, principal)
    try:
        metadata = await deck_service.get_deck_metadata(
            PostgresDeckStorage(session), startup=startup
        )
    except DeckNotFoundError:
        raise _deck_not_found() from None
    return DeckResponse.from_metadata(metadata)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, **_STATE_CHANGING)
async def delete_deck(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> Response:
    try:
        startup = await _load_owned_startup(session, startup_id, principal, for_update=True)
        await deck_service.delete_deck(session, PostgresDeckStorage(session), startup=startup)
        await session.commit()
    except StartupLockedError:
        await session.rollback()
        raise _startup_locked_error() from None
    except DeckNotFoundError:
        await session.rollback()
        raise _deck_not_found() from None
    except Exception:
        await session.rollback()
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
