"""Streaming multipart reader for pitch-deck uploads.

Reads the RAW request stream through python-multipart's push parser with a
hard byte cap, so the declared Content-Length is never consulted and an
oversized upload is abandoned the moment it crosses the limit — no partial
row, no unbounded buffering in memory or on disk.

Refusals raise DeckUploadError with a reason from a fixed catalogue; the
exception text never contains any uploaded byte, filename, or header value.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from python_multipart.multipart import MultipartParser, parse_options_header

from app.models.pitch_deck import MAX_DECK_BYTES

# The PDF may legitimately be exactly MAX_DECK_BYTES; the whole multipart
# body gets this much extra room for boundaries, part headers, and small
# sibling fields before the flood protection trips.
_BODY_SLACK = 64 * 1024

_FILE_FIELD = b"file"


class DeckUploadError(Exception):
    """Refused upload. `reason` comes from a fixed catalogue, never user input."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"deck upload refused: {reason}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class UploadedDeck:
    """Raw upload as received; filename/MIME are UNSANITIZED caller input."""

    filename: str | None
    declared_mime: str | None
    content: bytes


class _FilePartCollector:
    """Push-parser callbacks that buffer only the `file` part, capped."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self.parts_seen = 0
        self.found = False
        self.filename: str | None = None
        self.declared_mime: str | None = None
        self.content = b""
        self._headers: dict[bytes, bytes] = {}
        self._field = bytearray()
        self._value = bytearray()
        self._collecting = False
        self._buffer = bytearray()

    @property
    def callbacks(self) -> dict:
        return {
            "on_part_begin": self._on_part_begin,
            "on_header_field": self._on_header_field,
            "on_header_value": self._on_header_value,
            "on_header_end": self._on_header_end,
            "on_headers_finished": self._on_headers_finished,
            "on_part_data": self._on_part_data,
            "on_part_end": self._on_part_end,
        }

    def _on_part_begin(self) -> None:
        self.parts_seen += 1
        self._headers = {}

    def _on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._field += data[start:end]

    def _on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._value += data[start:end]

    def _on_header_end(self) -> None:
        self._headers[bytes(self._field).lower()] = bytes(self._value)
        self._field.clear()
        self._value.clear()

    def _on_headers_finished(self) -> None:
        _, params = parse_options_header(self._headers.get(b"content-disposition"))
        if self.found or params.get(b"name") != _FILE_FIELD:
            return
        self._collecting = True
        filename = params.get(b"filename")
        self.filename = filename.decode("utf-8", errors="replace") if filename else None
        mime = self._headers.get(b"content-type")
        self.declared_mime = mime.decode("latin-1") if mime is not None else None

    def _on_part_data(self, data: bytes, start: int, end: int) -> None:
        if not self._collecting:
            return
        self._buffer += data[start:end]
        if len(self._buffer) > self.max_bytes:
            raise DeckUploadError("too_large")

    def _on_part_end(self) -> None:
        if self._collecting:
            self._collecting = False
            self.found = True
            self.content = bytes(self._buffer)


async def read_deck_upload(
    stream: AsyncIterator[bytes], *, content_type: str | None, max_bytes: int = MAX_DECK_BYTES
) -> UploadedDeck:
    """Pull the `file` part out of a multipart stream under a hard byte cap."""
    media_type, params = parse_options_header(content_type)
    boundary = params.get(b"boundary")
    if media_type != b"multipart/form-data" or not boundary:
        raise DeckUploadError("not_multipart")

    collector = _FilePartCollector(max_bytes)
    parser = MultipartParser(boundary, collector.callbacks)
    total = 0
    async for chunk in stream:
        total += len(chunk)
        # Overall-body cap: sibling fields must not become a side channel for
        # flooding the server past the file limit.
        if total > max_bytes + _BODY_SLACK:
            raise DeckUploadError("too_large")
        try:
            parser.write(chunk)
        except DeckUploadError:
            raise
        except Exception:
            raise DeckUploadError("malformed") from None
        if collector.found:
            # The deck is complete; nothing after it is worth reading.
            return _result(collector)

    try:
        parser.finalize()
    except Exception:
        raise DeckUploadError("malformed") from None
    return _result(collector)


def _result(collector: _FilePartCollector) -> UploadedDeck:
    if not collector.parts_seen:
        raise DeckUploadError("malformed")
    if not collector.found:
        raise DeckUploadError("missing_file")
    return UploadedDeck(
        filename=collector.filename,
        declared_mime=collector.declared_mime,
        content=collector.content,
    )
