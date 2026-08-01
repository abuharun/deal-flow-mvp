"""Trusted-proxy-aware client IP resolution (Task B5, slice B2).

Security contract:
- The direct peer address is the only trusted input. X-Forwarded-For is
  parsed ONLY when that peer lies inside a configured trusted proxy CIDR;
  with the default empty configuration no proxy header is ever believed.
  The `Forwarded` header is never parsed at all.
- A trusted chain is bounded (length and hop count) and walked right-to-left
  across trusted hops; the first untrusted valid address is the client, so
  attacker-appended leftmost values can never win. Any malformed hop —
  ports, hostnames, brackets, `unknown`, control characters, empties —
  poisons the whole chain and falls back to the direct peer.
- The result is a normalized IP string (or a fixed sentinel for an absent or
  unparseable peer) used ONLY as an ephemeral rate-limiter bucket key; it is
  deliberately not logged or audited in this slice.
"""

import ipaddress
from collections.abc import Iterable, Sequence
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

from starlette.requests import Request

# A peer we cannot parse still needs a stable limiter bucket; this sentinel
# can never collide with a normalized IP string.
UNKNOWN_PEER = "unknown-peer"

# Real chains behind one or two proxies are tiny; anything bigger is noise
# or an attack and safely collapses to the direct peer.
MAX_FORWARDED_CHARS = 512
MAX_FORWARDED_HOPS = 10

_FORWARDED_FOR_HEADER = "x-forwarded-for"

Network = IPv4Network | IPv6Network
Address = IPv4Address | IPv6Address


def parse_trusted_proxies(cidrs: Iterable[str]) -> tuple[Network, ...]:
    """Parse validated CIDR strings (bare IPs become host networks); raises ValueError."""
    return tuple(ipaddress.ip_network(entry) for entry in cidrs)


def _parse_address(value: object) -> Address | None:
    # ip_address rejects ports, brackets, hostnames, `unknown`, and control
    # characters outright; only surrounding ASCII spaces are forgiven, so a
    # hop padded with \n, \r, \t or other control whitespace stays invalid
    # and poisons the chain.
    if not isinstance(value, str):
        return None
    try:
        return ipaddress.ip_address(value.strip(" "))
    except ValueError:
        return None


def _is_trusted(address: Address, trusted_proxies: Sequence[Network]) -> bool:
    # `in` is False across address families, so mixed v4/v6 checks are safe.
    return any(address in network for network in trusted_proxies)


def resolve_client_ip(
    *,
    peer: str | None,
    forwarded_for: str | None,
    trusted_proxies: Sequence[Network],
) -> str:
    """Resolve the effective client IP for rate limiting; never raises."""
    peer_address = _parse_address(peer)
    if peer_address is None:
        return UNKNOWN_PEER
    peer_ip = str(peer_address)
    if not trusted_proxies or not _is_trusted(peer_address, trusted_proxies):
        return peer_ip
    if forwarded_for is None or len(forwarded_for) > MAX_FORWARDED_CHARS:
        return peer_ip

    hops = forwarded_for.split(",")
    if len(hops) > MAX_FORWARDED_HOPS:
        return peer_ip
    parsed: list[Address] = []
    for hop in hops:
        address = _parse_address(hop)
        if address is None:
            # One bad hop makes the whole chain untrustworthy; guessing at
            # the valid remainder would let crafted chains steer the result.
            return peer_ip
        parsed.append(address)

    for address in reversed(parsed):
        if not _is_trusted(address, trusted_proxies):
            return str(address)
    # Every hop was one of our own proxies: no client identity survives.
    return peer_ip


def client_ip_for_request(request: Request) -> str:
    """The effective client IP for this request, from peer + configured proxies."""
    peer = request.client.host if request.client is not None else None
    return resolve_client_ip(
        peer=peer,
        forwarded_for=request.headers.get(_FORWARDED_FOR_HEADER),
        trusted_proxies=request.app.state.trusted_proxy_networks,
    )
