"""Trusted-proxy-aware client IP resolution (Task B5, slice B2).

Contracts under test:
- Settings.trusted_proxy_cidrs parses a comma-separated env value into a
  validated tuple; the default is empty, which means NO proxy header is ever
  trusted.
- resolve_client_ip parses the direct peer with `ipaddress` and ignores
  X-Forwarded-For entirely unless that peer lies inside a configured trusted
  proxy CIDR. When trusted, a bounded chain is walked right-to-left across
  trusted hops and the first untrusted valid address is the client.
- Malformed, control-character, overlong, port-carrying, hostname, `unknown`,
  bracketed, empty-hop, or over-long chains fall back safely to the direct
  peer. IPv4 and IPv6 both work; results are normalized IP strings.
- The `Forwarded` header is never parsed, and a spoofed X-Forwarded-For from
  an untrusted peer can never influence the result.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.config import Settings
from app.main import create_app
from app.security.client_ip import (
    MAX_FORWARDED_CHARS,
    MAX_FORWARDED_HOPS,
    UNKNOWN_PEER,
    client_ip_for_request,
    parse_trusted_proxies,
    resolve_client_ip,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

TRUSTED = parse_trusted_proxies(("127.0.0.1/32", "10.0.0.0/8", "fd00::/8"))
NO_PROXIES: tuple = ()


def resolve(peer, forwarded_for=None, trusted=TRUSTED) -> str:
    return resolve_client_ip(peer=peer, forwarded_for=forwarded_for, trusted_proxies=trusted)


class TestParseTrustedProxies:
    def test_empty_input_yields_empty_tuple(self):
        assert parse_trusted_proxies(()) == ()

    def test_cidrs_and_bare_addresses_parse_for_both_families(self):
        networks = parse_trusted_proxies(("10.0.0.0/8", "192.0.2.7", "fd00::/8", "2001:db8::1"))
        assert len(networks) == 4
        assert str(networks[1]) == "192.0.2.7/32", "a bare IP must become its /32 network"

    @pytest.mark.parametrize(
        "bad", ["evil.example", "10.0.0.0/33", "1.2.3.4:80", "unknown", "10.0.0.0/8; rm -rf"]
    )
    def test_invalid_entries_raise(self, bad):
        with pytest.raises(ValueError):
            parse_trusted_proxies((bad,))


class TestUntrustedPeer:
    def test_peer_is_returned_when_no_proxies_are_trusted(self):
        assert resolve("203.0.113.7", trusted=NO_PROXIES) == "203.0.113.7"

    def test_forwarded_for_is_ignored_without_trusted_proxies(self):
        assert resolve("203.0.113.7", "198.51.100.9", trusted=NO_PROXIES) == "203.0.113.7"

    def test_spoofed_forwarded_for_from_untrusted_peer_is_ignored(self):
        # 203.0.113.7 is not in any trusted CIDR, so its header is a lie.
        assert resolve("203.0.113.7", "10.0.0.5, 198.51.100.9") == "203.0.113.7"

    def test_ipv6_peer_is_normalized(self):
        assert resolve("2001:DB8:0:0:0:0:0:1", trusted=NO_PROXIES) == "2001:db8::1"

    @pytest.mark.parametrize("peer", [None, "", "not-an-ip", "203.0.113.7:443", "evil.example"])
    def test_missing_or_invalid_peer_yields_the_unknown_sentinel(self, peer):
        assert resolve(peer, "198.51.100.9") == UNKNOWN_PEER

    def test_unknown_sentinel_is_not_a_valid_ip_shape(self):
        # The sentinel is only ever a limiter bucket key; it must never be
        # confusable with a real normalized address.
        assert not any(ch.isdigit() for ch in UNKNOWN_PEER.replace("-", ""))


class TestTrustedProxyChain:
    def test_single_hop_returns_the_forwarded_client(self):
        assert resolve("127.0.0.1", "203.0.113.9") == "203.0.113.9"

    def test_walks_right_to_left_across_trusted_hops(self):
        # 10.0.0.5 is our proxy; the next hop out (203.0.113.9) is the client.
        # The leftmost value is attacker-controlled and must never be chosen.
        assert resolve("127.0.0.1", "198.51.100.7, 203.0.113.9, 10.0.0.5") == "203.0.113.9"

    def test_untrusted_rightmost_hop_wins_over_spoofed_leftmost(self):
        assert resolve("127.0.0.1", "1.2.3.4, 8.8.8.8") == "8.8.8.8"

    def test_fully_trusted_chain_falls_back_to_the_peer(self):
        assert resolve("127.0.0.1", "10.0.0.5, 10.0.0.6") == "127.0.0.1"

    def test_hop_whitespace_is_tolerated(self):
        assert resolve("127.0.0.1", "  203.0.113.9 ,  10.0.0.5  ") == "203.0.113.9"

    def test_ipv6_client_is_normalized(self):
        assert resolve("127.0.0.1", "2001:DB8::0001, 10.0.0.5") == "2001:db8::1"

    def test_ipv6_trusted_proxy_chain(self):
        assert resolve("fd00::1", "203.0.113.9, fd00::2") == "203.0.113.9"

    def test_missing_header_from_trusted_peer_returns_the_peer(self):
        assert resolve("127.0.0.1", None) == "127.0.0.1"


class TestMalformedChainsFallBack:
    @pytest.mark.parametrize(
        "chain",
        [
            "",
            "unknown, 10.0.0.5",
            "203.0.113.9:443, 10.0.0.5",  # ports are never accepted
            "[2001:db8::1]:443, 10.0.0.5",
            "[2001:db8::1], 10.0.0.5",  # brackets are not an IP
            "evil.example, 10.0.0.5",  # hostnames are never resolved
            "203.0.113.9, , 10.0.0.5",  # empty hop
            "203.0.113.9\x00, 10.0.0.5",  # control characters
            "999.999.1.1, 10.0.0.5",
            "203.0.113.9;10.0.0.5",
        ],
    )
    def test_any_invalid_hop_poisons_the_whole_chain(self, chain):
        assert resolve("127.0.0.1", chain) == "127.0.0.1"

    @pytest.mark.parametrize(
        "chain",
        [
            "203.0.113.9\n, 10.0.0.5",  # newline around a hop
            "\n203.0.113.9, 10.0.0.5",
            "203.0.113.9\r, 10.0.0.5",  # carriage return
            "203.0.113.9\t, 10.0.0.5",  # tab
            "\t203.0.113.9, 10.0.0.5",
            "203.0.113.9\x0b, 10.0.0.5",  # vertical tab
            "203.0.113.9\x0c, 10.0.0.5",  # form feed
            "203.0.113.9, 10.0.0.5\n",  # trailing control on the last hop
        ],
    )
    def test_control_whitespace_around_a_hop_poisons_the_chain(self, chain):
        # Only ordinary ASCII spaces may pad a hop; any control character —
        # even strippable ones like \n, \r, \t — must fall back to the peer.
        assert resolve("127.0.0.1", chain) == "127.0.0.1"

    def test_overlong_header_falls_back_to_the_peer(self):
        chain = "1.2.3.4, " * 400
        assert len(chain) > MAX_FORWARDED_CHARS
        assert resolve("127.0.0.1", chain) == "127.0.0.1"

    def test_too_many_hops_falls_back_to_the_peer(self):
        hops = ["203.0.113.9"] + ["10.0.0.5"] * MAX_FORWARDED_HOPS
        assert resolve("127.0.0.1", ", ".join(hops)) == "127.0.0.1"

    def test_hop_count_at_the_bound_is_accepted(self):
        hops = ["203.0.113.9"] + ["10.0.0.5"] * (MAX_FORWARDED_HOPS - 1)
        assert resolve("127.0.0.1", ", ".join(hops)) == "203.0.113.9"


def make_request(app, peer, headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/login",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 40000) if peer is not None else None,
        "app": app,
    }
    return Request(scope)


def make_app(trusted_proxy_cidrs: str = ""):
    settings = Settings(_env_file=None, env="test", trusted_proxy_cidrs=trusted_proxy_cidrs)
    return create_app(settings)


class TestRequestLevelResolution:
    def test_default_settings_trust_no_proxy_headers(self):
        request = make_request(make_app(), "203.0.113.7", {"x-forwarded-for": "198.51.100.9"})
        assert client_ip_for_request(request) == "203.0.113.7"

    def test_trusted_peer_yields_forwarded_client(self):
        app = make_app("127.0.0.1/32")
        request = make_request(app, "127.0.0.1", {"x-forwarded-for": "203.0.113.9"})
        assert client_ip_for_request(request) == "203.0.113.9"

    def test_forwarded_header_is_never_parsed_even_from_a_trusted_peer(self):
        app = make_app("127.0.0.1/32")
        request = make_request(app, "127.0.0.1", {"forwarded": "for=203.0.113.9"})
        assert client_ip_for_request(request) == "127.0.0.1"

    def test_request_without_a_client_yields_the_unknown_sentinel(self):
        request = make_request(make_app(), None, {})
        assert client_ip_for_request(request) == UNKNOWN_PEER


class TestSettingsTrustedProxyCidrs:
    def test_default_is_empty(self):
        assert Settings(_env_file=None, env="test").trusted_proxy_cidrs == ()

    def test_comma_separated_env_value_is_split_and_stripped(self):
        settings = Settings(
            _env_file=None, env="test", trusted_proxy_cidrs=" 10.0.0.0/8 , fd00::/8 "
        )
        assert settings.trusted_proxy_cidrs == ("10.0.0.0/8", "fd00::/8")

    @pytest.mark.parametrize("bad", ["evil.example", "10.0.0.0/33", "1.2.3.4:80, 10.0.0.0/8"])
    def test_invalid_cidrs_are_rejected(self, bad):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, env="test", trusted_proxy_cidrs=bad)

    def test_env_example_documents_the_placeholder(self):
        content = (BACKEND_DIR / ".env.example").read_text()
        assert "TRUSTED_PROXY_CIDRS=" in content
