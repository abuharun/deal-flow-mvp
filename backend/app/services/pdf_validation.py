"""Pitch-deck PDF validation and filename sanitization.

Security contract:
- Every refusal raises DeckValidationError with a reason drawn from a fixed
  catalogue; the exception text never contains the filename, the declared
  MIME, or any uploaded byte, so it is safe to log and to map onto the
  canonical API error envelope.
- The sanitized filename is the ONLY form that may be stored or echoed:
  path components, control/CR/LF characters, invisible bidi/format
  characters, quotes, and backslashes are removed, and the result is bounded
  and always ends in .pdf.
"""

import hashlib
import unicodedata
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from app.models.pitch_deck import DECK_MIME_TYPE, MAX_DECK_BYTES, MAX_DECK_PAGES

MAX_SANITIZED_FILENAME = 255
_PDF_MAGIC = b"%PDF-"
_PDF_SUFFIX = ".pdf"
_FALLBACK_STEM = "deck"

# Characters that enable header/log injection or rendering tricks even after
# path splitting: double quote (header quoting), backslash (escape/path).
_DANGEROUS_CHARS = frozenset('"\\')


class DeckValidationError(Exception):
    """Refused deck. `reason` comes from a fixed catalogue, never user input."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"deck validation failed: {reason}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class DeckFile:
    """Validated deck metadata; content bytes travel separately on purpose."""

    filename: str
    size_bytes: int
    sha256: bytes
    page_count: int


def _basename(raw: str) -> str:
    # Both separators, always: a Windows browser sends backslash paths.
    return raw.replace("\\", "/").rsplit("/", 1)[-1]


def _is_forbidden_char(char: str) -> bool:
    # Cc = control (includes CR/LF/NUL/ESC), Cf = format (bidi overrides,
    # zero-width characters, and every other invisible direction trick).
    return char in _DANGEROUS_CHARS or unicodedata.category(char) in ("Cc", "Cf")


def sanitize_filename(raw: str | None) -> str:
    """A bounded, header- and log-safe display name that always ends in .pdf."""
    name = _basename(raw or "")
    name = "".join(char for char in name if not _is_forbidden_char(char))
    # Preserve the caller's extension casing (.PDF stays .PDF) when present.
    if name.lower().endswith(_PDF_SUFFIX):
        stem, suffix = name[: -len(_PDF_SUFFIX)], name[-len(_PDF_SUFFIX) :]
    else:
        stem, suffix = name, _PDF_SUFFIX
    stem = stem.strip().strip(".").strip() or _FALLBACK_STEM
    stem = stem[: MAX_SANITIZED_FILENAME - len(_PDF_SUFFIX)].strip().strip(".").strip()
    return (stem or _FALLBACK_STEM) + suffix


def validate_deck(content: bytes, *, filename: str | None, declared_mime: str | None) -> DeckFile:
    """Run every deck check in a fixed order and return storable metadata."""
    if not content:
        raise DeckValidationError("empty")
    if len(content) > MAX_DECK_BYTES:
        raise DeckValidationError("too_large")
    if not filename or not _basename(filename).lower().endswith(_PDF_SUFFIX):
        raise DeckValidationError("bad_extension")
    if declared_mime != DECK_MIME_TYPE:
        raise DeckValidationError("bad_mime")
    if not content.startswith(_PDF_MAGIC):
        raise DeckValidationError("not_pdf")

    try:
        reader = PdfReader(BytesIO(content), strict=False)
    except Exception:
        raise DeckValidationError("malformed") from None
    if reader.is_encrypted:
        raise DeckValidationError("encrypted")
    try:
        page_count = len(reader.pages)
    except Exception:
        raise DeckValidationError("malformed") from None
    if not 1 <= page_count <= MAX_DECK_PAGES:
        raise DeckValidationError("page_count")

    return DeckFile(
        filename=sanitize_filename(filename),
        size_bytes=len(content),
        sha256=hashlib.sha256(content).digest(),
        page_count=page_count,
    )
