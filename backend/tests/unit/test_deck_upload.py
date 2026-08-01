"""Streaming multipart reader for pitch-deck uploads (pure unit tests).

Contracts under test:
- The reader consumes the raw request stream chunk by chunk and never looks
  at Content-Length; the hard cap fires on actual bytes.
- A file part that grows past the cap aborts the read IMMEDIATELY — the rest
  of the stream is never pulled, so an attacker cannot make the server buffer
  an arbitrarily large body anywhere (memory or disk).
- Exactly 5 MiB of file bytes pass through the reader untouched.
- Non-multipart bodies, bodies without a `file` field, and malformed
  multipart framing are refused with canonical reasons that echo nothing.
"""

from collections.abc import AsyncIterator

import pytest

from app.services.deck_upload import DeckUploadError, read_deck_upload
from app.services.pdf_validation import MAX_DECK_BYTES

BOUNDARY = "deckboundary123"
CONTENT_TYPE = f"multipart/form-data; boundary={BOUNDARY}"


def multipart_body(
    content: bytes,
    *,
    filename: str = "deck.pdf",
    mime: str = "application/pdf",
    field: str = "file",
    extra_parts: bytes = b"",
) -> bytes:
    return (
        extra_parts
        + f"--{BOUNDARY}\r\n".encode()
        + (
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{BOUNDARY}--\r\n".encode()
    )


class ChunkStream:
    """Async byte stream that records how much of itself was consumed."""

    def __init__(self, body: bytes, chunk_size: int = 64 * 1024) -> None:
        self.chunks = [body[i : i + chunk_size] for i in range(0, len(body), chunk_size)]
        self.consumed = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.consumed += 1
            yield chunk


async def read(body: bytes, content_type: str | None = CONTENT_TYPE, **kwargs):
    stream = ChunkStream(body).__aiter__()
    return await read_deck_upload(stream, content_type=content_type, **kwargs)


class TestHappyPath:
    async def test_file_part_roundtrips_bytes_filename_and_mime(self):
        content = b"%PDF-1.4 pretend deck bytes"
        upload = await read(multipart_body(content, filename="My Deck.pdf"))
        assert upload.content == content
        assert upload.filename == "My Deck.pdf"
        assert upload.declared_mime == "application/pdf"

    async def test_exactly_five_mib_of_file_bytes_is_read_in_full(self):
        content = b"a" * MAX_DECK_BYTES
        upload = await read(multipart_body(content))
        assert len(upload.content) == MAX_DECK_BYTES

    async def test_utf8_filename_survives(self):
        upload = await read(multipart_body(b"x", filename="старт.pdf"))
        assert upload.filename == "старт.pdf"

    async def test_other_fields_before_the_file_are_ignored(self):
        extra = (
            f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="note"\r\n\r\nhello\r\n'
        ).encode()
        upload = await read(multipart_body(b"content", extra_parts=extra))
        assert upload.content == b"content"


class TestRefusals:
    @pytest.mark.parametrize("content_type", [None, "", "application/json", "multipart/form-data"])
    async def test_non_multipart_or_missing_boundary_is_refused(self, content_type):
        with pytest.raises(DeckUploadError) as excinfo:
            await read(multipart_body(b"x"), content_type=content_type)
        assert excinfo.value.reason == "not_multipart"

    async def test_body_without_a_file_field_is_refused(self):
        with pytest.raises(DeckUploadError) as excinfo:
            await read(multipart_body(b"x", field="attachment"))
        assert excinfo.value.reason == "missing_file"

    async def test_garbage_body_is_refused(self):
        with pytest.raises(DeckUploadError) as excinfo:
            await read(b"this is not multipart at all")
        assert excinfo.value.reason == "malformed"

    async def test_empty_body_is_refused(self):
        with pytest.raises(DeckUploadError) as excinfo:
            await read(b"")
        assert excinfo.value.reason == "malformed"


class TestEarlyHardCap:
    async def test_file_one_byte_over_the_cap_is_refused(self):
        body = multipart_body(b"a" * (MAX_DECK_BYTES + 1))
        with pytest.raises(DeckUploadError) as excinfo:
            await read(body)
        assert excinfo.value.reason == "too_large"

    async def test_oversized_stream_is_abandoned_before_it_is_fully_read(self):
        # 32 MiB body: the reader must stop within a chunk or two of the cap,
        # never consuming anything close to the whole stream.
        body = multipart_body(b"a" * (32 * 1024 * 1024))
        stream = ChunkStream(body)
        with pytest.raises(DeckUploadError) as excinfo:
            await read_deck_upload(stream.__aiter__(), content_type=CONTENT_TYPE)
        assert excinfo.value.reason == "too_large"
        cap_chunks = MAX_DECK_BYTES // (64 * 1024)
        assert stream.consumed <= cap_chunks + 2, "must abort reading at the cap"
        assert stream.consumed < len(stream.chunks) // 2

    async def test_huge_non_file_parts_cannot_bloat_the_body_either(self):
        # The overall body cap must also stop a flood arriving before the
        # file part (e.g. a gigantic text field).
        extra = (
            (f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="note"\r\n\r\n').encode()
            + b"b" * (32 * 1024 * 1024)
            + b"\r\n"
        )
        body = multipart_body(b"x", extra_parts=extra)
        stream = ChunkStream(body)
        with pytest.raises(DeckUploadError) as excinfo:
            await read_deck_upload(stream.__aiter__(), content_type=CONTENT_TYPE)
        assert excinfo.value.reason == "too_large"
        assert stream.consumed < len(stream.chunks) // 2
