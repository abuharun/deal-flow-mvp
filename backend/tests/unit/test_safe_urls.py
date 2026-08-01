"""Safe HTTP(S) URL normalization for founder-supplied dataroom links.

Follows the project's origin policy (app.security.origins): parsed-and-
normalized comparison, no credentials, no control characters or whitespace,
no fragments, http/https only. The validator raises ValueError with a fixed
message that never echoes the rejected value.
"""

import pytest

from app.security.urls import MAX_URL_LENGTH, normalize_safe_http_url

SAFE = [
    ("https://drive.example.com/folder/abc?usp=sharing", None),
    ("http://data.example.com", None),
    # Scheme and host are case-normalized; path and query survive verbatim.
    ("HTTPS://Drive.Example.COM/Folder/AbC?X=1", "https://drive.example.com/Folder/AbC?X=1"),
    ("https://data.example.com:8443/room", None),
]

UNSAFE = [
    "javascript:alert(1)",
    "data:text/html;base64,xxxx",
    "ftp://files.example.com/room",
    "file:///etc/passwd",
    "//drive.example.com/folder",  # scheme-relative
    "https://",  # no host
    "https://user:pass@drive.example.com/folder",  # credentials
    "https://user@drive.example.com/folder",  # bare userinfo
    "https://drive.example.com/folder#fragment",
    "https://drive.example.com/fol der",  # whitespace
    "https://drive.example.com/fol\x00der",  # control character
    "https://drive.example.com/folder\n",
    "https://drive.example.com:99999/",  # out-of-range port
    "not a url",
    "",
]


@pytest.mark.parametrize(("value", "expected"), SAFE)
def test_safe_urls_normalize(value, expected):
    assert normalize_safe_http_url(value) == (expected if expected is not None else value)


@pytest.mark.parametrize("value", UNSAFE)
def test_unsafe_urls_are_rejected_without_echoing_the_value(value):
    with pytest.raises(ValueError) as excinfo:
        normalize_safe_http_url(value)
    if value.strip():
        assert value not in str(excinfo.value), "the rejected URL must never be echoed"


def test_overlong_urls_are_rejected():
    url = "https://drive.example.com/" + "a" * MAX_URL_LENGTH
    with pytest.raises(ValueError):
        normalize_safe_http_url(url)
