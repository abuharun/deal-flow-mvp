"""Pitch-deck PDF validation and filename sanitization (pure unit tests).

Contracts under test:
- Exactly 5 MiB of otherwise-valid PDF is accepted; one byte more is refused.
- Empty uploads, wrong extensions, wrong declared MIME, missing %PDF- magic,
  malformed/truncated bodies, encrypted PDFs, and page counts outside 1..15
  are each refused with a canonical machine reason that never echoes any
  user-controlled value (filename, MIME string, or bytes).
- Filenames are stripped of path components, control/CR/LF characters, bidi
  and other invisible format characters, and dangerous quotes; the sanitized
  value is bounded and always ends in .pdf.
- The returned metadata carries the exact byte size and SHA-256.
"""

import hashlib
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.services.pdf_validation import (
    MAX_DECK_BYTES,
    DeckValidationError,
    sanitize_filename,
    validate_deck,
)


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
    """Grow a PDF to an exact size with a trailing comment (still parseable)."""
    padding = target_size - len(pdf) - 2
    assert padding >= 0, "target below base PDF size"
    return pdf + b"\n%" + b"0" * padding


def validate(content: bytes, filename: str = "deck.pdf", mime: str = "application/pdf"):
    return validate_deck(content, filename=filename, declared_mime=mime)


def assert_refused(reason: str, content: bytes, **kwargs) -> DeckValidationError:
    with pytest.raises(DeckValidationError) as excinfo:
        validate(content, **kwargs)
    assert excinfo.value.reason == reason
    return excinfo.value


class TestValidDecks:
    def test_valid_one_page_pdf_yields_exact_metadata(self):
        content = make_pdf(pages=1)
        deck = validate(content, filename="My Deck.pdf")
        assert deck.filename == "My Deck.pdf"
        assert deck.size_bytes == len(content)
        assert deck.sha256 == hashlib.sha256(content).digest()
        assert deck.page_count == 1

    def test_exactly_five_mib_is_accepted(self):
        content = pad_pdf(make_pdf(), MAX_DECK_BYTES)
        assert len(content) == MAX_DECK_BYTES
        deck = validate(content)
        assert deck.size_bytes == MAX_DECK_BYTES

    def test_fifteen_pages_is_accepted(self):
        deck = validate(make_pdf(pages=15))
        assert deck.page_count == 15

    def test_uppercase_extension_is_accepted(self):
        deck = validate(make_pdf(), filename="DECK.PDF")
        assert deck.filename == "DECK.PDF"


class TestRefusedDecks:
    def test_empty_upload_is_refused(self):
        assert_refused("empty", b"")

    def test_one_byte_over_five_mib_is_refused(self):
        content = pad_pdf(make_pdf(), MAX_DECK_BYTES + 1)
        assert_refused("too_large", content)

    @pytest.mark.parametrize("filename", ["deck.txt", "deck.pdf.exe", "deck", ""])
    def test_non_pdf_extension_is_refused(self, filename):
        assert_refused("bad_extension", make_pdf(), filename=filename)

    def test_missing_filename_is_refused(self):
        with pytest.raises(DeckValidationError) as excinfo:
            validate_deck(make_pdf(), filename=None, declared_mime="application/pdf")
        assert excinfo.value.reason == "bad_extension"

    @pytest.mark.parametrize(
        "mime", ["text/plain", "application/x-pdf", "application/pdf; charset=x", "", None]
    )
    def test_non_pdf_declared_mime_is_refused(self, mime):
        with pytest.raises(DeckValidationError) as excinfo:
            validate_deck(make_pdf(), filename="deck.pdf", declared_mime=mime)
        assert excinfo.value.reason == "bad_mime"

    def test_leading_junk_before_magic_is_refused(self):
        assert_refused("not_pdf", b"JUNK" + make_pdf())

    def test_magic_alone_without_structure_is_refused(self):
        assert_refused("malformed", b"%PDF-1.4 garbage garbage garbage")

    def test_truncated_pdf_is_refused(self):
        assert_refused("malformed", make_pdf()[:100])

    def test_encrypted_pdf_is_refused(self):
        assert_refused("encrypted", make_pdf(password="secret"))

    def test_zero_page_pdf_is_refused(self):
        assert_refused("page_count", make_pdf(pages=0))

    def test_sixteen_pages_is_refused(self):
        assert_refused("page_count", make_pdf(pages=16))

    def test_errors_never_echo_the_filename_or_mime(self):
        hostile_name = "../../etc/passwd\r\nX-Evil: 1.pdf"
        hostile_mime = "text/hostile-mime"
        with pytest.raises(DeckValidationError) as excinfo:
            validate_deck(make_pdf(), filename=hostile_name, declared_mime=hostile_mime)
        text = repr(excinfo.value) + str(excinfo.value)
        assert "passwd" not in text
        assert "X-Evil" not in text
        assert hostile_mime not in text


class TestSanitizeFilename:
    def test_plain_name_is_preserved(self):
        assert sanitize_filename("Q3 Deck v2.pdf") == "Q3 Deck v2.pdf"

    @pytest.mark.parametrize(
        "raw",
        [
            "../../../etc/deck.pdf",
            "..\\..\\windows\\deck.pdf",
            "/absolute/path/deck.pdf",
            "C:\\Users\\evil\\deck.pdf",
        ],
    )
    def test_path_components_are_stripped(self, raw):
        assert sanitize_filename(raw) == "deck.pdf"

    def test_crlf_and_control_characters_are_removed(self):
        assert sanitize_filename('de\r\nck\x00\x1b"; evil.pdf') == "deck; evil.pdf"

    def test_bidi_and_invisible_format_characters_are_removed(self):
        # RLO trickery: "deck\u202efdp.gnp" renders reversed; the override
        # must be dropped so the stored name has no direction-changing chars.
        assert "\u202e" not in sanitize_filename("deck\u202e.pdf")
        assert "\u200b" not in sanitize_filename("de\u200bck.pdf")

    def test_dangerous_quotes_and_backslashes_are_removed(self):
        sanitized = sanitize_filename('a"b\\c.pdf')
        assert '"' not in sanitized
        assert "\\" not in sanitized
        assert sanitized.endswith(".pdf")

    def test_long_names_are_bounded_and_keep_the_pdf_suffix(self):
        sanitized = sanitize_filename("x" * 1000 + ".pdf")
        assert len(sanitized) <= 255
        assert sanitized.lower().endswith(".pdf")

    def test_name_reduced_to_nothing_falls_back_to_deck_pdf(self):
        assert sanitize_filename('"\r\n\u202e".pdf') == "deck.pdf"
        assert sanitize_filename("....pdf") == "deck.pdf"

    def test_unicode_letters_survive(self):
        assert sanitize_filename("prezentatsiya-старт.pdf") == "prezentatsiya-старт.pdf"
