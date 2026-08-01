"""Validated web-origin model for route-level Origin checks (Task B4).

/auth/refresh and /auth/logout act on an ambient credential (the refresh
cookie), so before B5 adds general CORS they each demand an Origin header
that EQUALS one configured frontend origin. Equality is structural — parsed
scheme/host/port with per-scheme default ports normalized — never substring,
prefix, or suffix matching, so `https://app.example.evil.com` and
`https://evil.com/https://app.example` can never slip through. `null`,
missing, and unparseable Origins all simply fail to parse.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}
# Whitespace and control characters are never valid inside a serialized
# origin; rejecting them up front also keeps urlsplit's quirks out of scope.
_FORBIDDEN_CHARS = re.compile(r"[\s\x00-\x1f\x7f]")
_MAX_ORIGIN_LENGTH = 256


@dataclass(frozen=True, slots=True)
class WebOrigin:
    """One parsed, normalized web origin: lowercase scheme/host, explicit port."""

    scheme: str
    host: str
    port: int

    @classmethod
    def parse(cls, value: object) -> "WebOrigin | None":
        """Parse a serialized origin, or None for anything else — never raises."""
        if not isinstance(value, str) or not value or len(value) > _MAX_ORIGIN_LENGTH:
            return None
        if _FORBIDDEN_CHARS.search(value):
            return None
        try:
            parts = urlsplit(value)
            # .port raises ValueError on non-numeric or out-of-range ports.
            hostname, port = parts.hostname, parts.port
            has_userinfo = parts.username is not None or parts.password is not None
        except ValueError:
            return None
        if parts.scheme not in _DEFAULT_PORTS or not hostname or has_userinfo:
            return None
        # A bare origin has no path, query, or fragment — "/" included.
        if parts.path or parts.query or parts.fragment:
            return None
        return cls(
            scheme=parts.scheme,
            host=hostname,
            port=port if port is not None else _DEFAULT_PORTS[parts.scheme],
        )


def origin_allowed(value: object, allowed: Iterable[str]) -> bool:
    """True only when `value` parses and equals one allowed origin structurally."""
    presented = WebOrigin.parse(value)
    if presented is None:
        return False
    return any(WebOrigin.parse(entry) == presented for entry in allowed)
