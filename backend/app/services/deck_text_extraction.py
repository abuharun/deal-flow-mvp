"""Bounded, safe pitch-deck text extraction for the analysis worker.

Deck bytes already passed `app.services.pdf_validation.validate_deck` at
upload time (page/size bounds enforced there), but this module re-parses
defensively anyway -- a worker may run long after upload and must never
trust stored bytes blindly. Same posture as pdf_validation: pypdf with
`strict=False`, explicit encrypted/malformed handling, and a fixed-catalogue
error whose text never carries filename/bytes/provider-visible detail.

The returned text is UNTRUSTED DATA: it travels into the provider prompt
labeled as such by the snapshot builder, never as instructions.
"""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from app.models.pitch_deck import MAX_DECK_BYTES, MAX_DECK_PAGES

# Pilot cap on deck text fed to the provider -- keeps prompt size (and cost)
# bounded regardless of how much text a 15-page deck actually contains.
MAX_EXTRACTED_TEXT_CHARS = 20_000


class DeckTextExtractionError(Exception):
    """Refused deck text. `reason` comes from a fixed catalogue, never user input."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"deck text extraction failed: {reason}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ExtractedDeckText:
    text: str
    truncated: bool


def extract_deck_text(
    content: bytes, *, max_chars: int = MAX_EXTRACTED_TEXT_CHARS
) -> ExtractedDeckText:
    """Return bounded, page-joined text, or raise DeckTextExtractionError.

    Re-checks the same size/page bounds `validate_deck` enforced at upload
    time -- defensively, since this reads bytes a worker fetched from
    storage long after upload, never trusting they're still within bounds.
    """
    if len(content) > MAX_DECK_BYTES:
        raise DeckTextExtractionError("too_large")

    try:
        reader = PdfReader(BytesIO(content), strict=False)
    except Exception:
        raise DeckTextExtractionError("malformed") from None
    if reader.is_encrypted:
        raise DeckTextExtractionError("encrypted")

    try:
        pages = reader.pages
        if not 1 <= len(pages) <= MAX_DECK_PAGES:
            raise DeckTextExtractionError("page_count")
        page_texts = [page.extract_text() or "" for page in pages]
    except DeckTextExtractionError:
        raise
    except Exception:
        raise DeckTextExtractionError("malformed") from None

    joined = "\n\n".join(page_text.strip() for page_text in page_texts if page_text.strip())
    if not joined:
        raise DeckTextExtractionError("no_extractable_text")

    if len(joined) > max_chars:
        return ExtractedDeckText(text=joined[:max_chars], truncated=True)
    return ExtractedDeckText(text=joined, truncated=False)
