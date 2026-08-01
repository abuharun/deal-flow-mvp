"""Bounded, safe deck text extraction (pure unit tests, no DB/network)."""

from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.services.deck_text_extraction import (
    MAX_EXTRACTED_TEXT_CHARS,
    DeckTextExtractionError,
    extract_deck_text,
)


def make_text_pdf(lines: list[str]) -> bytes:
    """A minimal, hand-built one-page PDF with a real extractable text stream."""
    content = (
        "BT /F1 24 Tf 100 700 Td " + " ".join(f"({line}) Tj 0 -30 Td" for line in lines) + " ET"
    )
    content_bytes = content.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content_bytes) + content_bytes + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref_offset}\n%%EOF".encode()
    return bytes(out)


def make_blank_pdf(pages: int = 1, *, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if password is not None:
        writer.encrypt(password)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestValidExtraction:
    def test_extracts_text_from_real_pdf(self):
        result = extract_deck_text(make_text_pdf(["Hello World", "Second line"]))
        assert "Hello World" in result.text
        assert "Second line" in result.text
        assert result.truncated is False

    def test_bounded_output_is_truncated_not_rejected(self):
        long_line = "A" * (MAX_EXTRACTED_TEXT_CHARS + 500)
        result = extract_deck_text(make_text_pdf([long_line]), max_chars=MAX_EXTRACTED_TEXT_CHARS)
        assert len(result.text) == MAX_EXTRACTED_TEXT_CHARS
        assert result.truncated is True


class TestRefusedDecks:
    def test_blank_pages_with_no_text_are_refused(self):
        with pytest.raises(DeckTextExtractionError) as excinfo:
            extract_deck_text(make_blank_pdf(pages=2))
        assert excinfo.value.reason == "no_extractable_text"

    def test_encrypted_pdf_is_refused(self):
        with pytest.raises(DeckTextExtractionError) as excinfo:
            extract_deck_text(make_blank_pdf(password="secret"))
        assert excinfo.value.reason == "encrypted"

    def test_malformed_pdf_is_refused(self):
        with pytest.raises(DeckTextExtractionError) as excinfo:
            extract_deck_text(b"%PDF-1.4 not really a pdf")
        assert excinfo.value.reason == "malformed"

    def test_truncated_pdf_bytes_are_refused(self):
        with pytest.raises(DeckTextExtractionError) as excinfo:
            extract_deck_text(make_text_pdf(["Hello"])[:40])
        assert excinfo.value.reason == "malformed"

    def test_errors_never_echo_pdf_content(self):
        secret_pdf = make_text_pdf(["SUPER SECRET FOUNDER DATA"])[:60]
        with pytest.raises(DeckTextExtractionError) as excinfo:
            extract_deck_text(secret_pdf)
        text = repr(excinfo.value) + str(excinfo.value)
        assert "SUPER SECRET" not in text
