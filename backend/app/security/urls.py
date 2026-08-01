"""Safe HTTP(S) URL validation for founder-supplied links (dataroom etc.).

Same posture as app.security.origins: parse structurally, allow only http and
https, reject credentials, control characters, whitespace, and fragments.
Rejections raise ValueError with a FIXED message — the offending value must
never travel back in an error (our validation summaries would exclude it, but
defense in depth costs nothing here).
"""

import re
from urllib.parse import urlsplit, urlunsplit

MAX_URL_LENGTH = 2048

_ALLOWED_SCHEMES = frozenset({"http", "https"})
# Whitespace and control characters are never valid inside a URL we would
# store; rejecting them up front also keeps urlsplit's quirks out of scope.
_FORBIDDEN_CHARS = re.compile(r"[\s\x00-\x1f\x7f]")

_REJECT_MESSAGE = "must be a plain http(s) URL without credentials or fragments"


def normalize_safe_http_url(value: str) -> str:
    """Return `value` with scheme/host lowercased, or raise ValueError.

    The error message is fixed and never contains the rejected value.
    """
    if not value or len(value) > MAX_URL_LENGTH or _FORBIDDEN_CHARS.search(value):
        raise ValueError(_REJECT_MESSAGE)
    try:
        parts = urlsplit(value)
        # .port raises ValueError on non-numeric or out-of-range ports.
        hostname, port = parts.hostname, parts.port
        has_userinfo = parts.username is not None or parts.password is not None
    except ValueError:
        raise ValueError(_REJECT_MESSAGE) from None
    if parts.scheme.lower() not in _ALLOWED_SCHEMES or not hostname or has_userinfo:
        raise ValueError(_REJECT_MESSAGE)
    if parts.fragment:
        raise ValueError(_REJECT_MESSAGE)
    netloc = hostname if port is None else f"{hostname}:{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, ""))
