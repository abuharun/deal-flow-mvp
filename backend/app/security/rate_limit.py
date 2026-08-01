"""Bounded in-memory rate limiting for the public auth endpoints (Task B5, slice B3).

This is explicitly single-process pilot protection: each app instance owns
one limiter in app.state and nothing is shared across processes, so a
Redis-backed (or otherwise shared) limiter is REQUIRED before the backend
scales horizontally.

Security contract:
- Keys are opaque `scope:kind:sha256hex` strings built with domain-separated
  SHA-256 over canonicalized input (emails lowercased/stripped); the raw
  email/token/IP never becomes a key and never leaves this module. Python's
  randomized hash() is never used.
- A hit checks EVERY key first and only then charges them all under one
  lock, so concurrent requests cannot exceed a limit and a request rejected
  by any key consumes nothing on the others (a retry that is allowed later
  still gets its full budget on every key).
- The key table is bounded: at capacity, deterministic pruning drops fully
  expired keys first, then the oldest surviving key is evicted. No
  background task exists; all upkeep happens inline.
"""

import asyncio
import hashlib
import math
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import MappingProxyType

# Versioned domain separation: these digests must never collide with any
# other SHA-256 use in the app (email tokens, refresh tokens, ...).
_KEY_DOMAIN = "bevosita.rate-limit.v1"

DEFAULT_MAX_KEYS = 10_000


@dataclass(frozen=True, slots=True)
class RatePolicy:
    """A frozen limit/window pair; policies are module constants, never runtime data."""

    limit: int
    window_seconds: float


@dataclass(frozen=True, slots=True)
class RateCharge:
    """One key to check-and-charge under a policy."""

    key: str
    policy: RatePolicy


class RateLimitExceeded(Exception):
    """Raised when any charged key is over its limit; retry_after is a positive int."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limit exceeded, retry after {retry_after}s")
        self.retry_after = retry_after


class _Bucket:
    """Sliding-window hit timestamps for one key (monotonic clock values)."""

    __slots__ = ("hits", "window")

    def __init__(self, window: float) -> None:
        self.hits: deque[float] = deque()
        self.window = window

    def prune(self, now: float) -> None:
        while self.hits and self.hits[0] + self.window <= now:
            self.hits.popleft()

    def expired(self, now: float) -> bool:
        return not self.hits or self.hits[-1] + self.window <= now

    def retry_after(self, now: float) -> int:
        remaining = self.hits[0] + self.window - now
        return max(1, math.ceil(remaining))


class RateLimiter:
    """Async concurrency-safe fixed-memory sliding-window limiter."""

    def __init__(
        self,
        *,
        max_keys: int = DEFAULT_MAX_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_keys = max_keys
        self._clock = clock
        self._lock = asyncio.Lock()
        # Insertion/refresh order doubles as the eviction order (LRU-ish).
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()

    @property
    def tracked_keys(self) -> int:
        return len(self._buckets)

    async def hit(self, charges: Sequence[RateCharge]) -> None:
        """Check all keys, then charge all keys — atomically under one lock.

        Raises RateLimitExceeded (with the largest blocking retry_after)
        without charging anything if ANY key is over its limit.
        """
        async with self._lock:
            now = self._clock()
            retry_after = 0
            for charge in charges:
                bucket = self._buckets.get(charge.key)
                if bucket is None:
                    continue
                bucket.prune(now)
                if len(bucket.hits) >= charge.policy.limit:
                    retry_after = max(retry_after, bucket.retry_after(now))
            if retry_after:
                raise RateLimitExceeded(retry_after=retry_after)
            for charge in charges:
                self._charge_one(charge, now)

    def _charge_one(self, charge: RateCharge, now: float) -> None:
        bucket = self._buckets.get(charge.key)
        if bucket is None:
            self._make_room(now)
            bucket = _Bucket(charge.policy.window_seconds)
            self._buckets[charge.key] = bucket
        else:
            self._buckets.move_to_end(charge.key)
        bucket.hits.append(now)

    def _make_room(self, now: float) -> None:
        if len(self._buckets) < self._max_keys:
            return
        expired = [key for key, bucket in self._buckets.items() if bucket.expired(now)]
        for key in expired:
            del self._buckets[key]
        while len(self._buckets) >= self._max_keys:
            self._buckets.popitem(last=False)


# --- Auth endpoint policies (frozen; see the task plan for the rationale) ---

LOGIN_SCOPE = "auth.login"
FORGOT_PASSWORD_SCOPE = "auth.forgot_password"
ACTIVATE_INVITE_SCOPE = "auth.activate_invite"
VERIFY_EMAIL_SCOPE = "auth.verify_email"
RESET_PASSWORD_SCOPE = "auth.reset_password"
REFRESH_SCOPE = "auth.refresh"

AUTH_POLICIES = MappingProxyType(
    {
        LOGIN_SCOPE: RatePolicy(limit=5, window_seconds=60),
        FORGOT_PASSWORD_SCOPE: RatePolicy(limit=3, window_seconds=3600),
        ACTIVATE_INVITE_SCOPE: RatePolicy(limit=10, window_seconds=3600),
        VERIFY_EMAIL_SCOPE: RatePolicy(limit=10, window_seconds=3600),
        RESET_PASSWORD_SCOPE: RatePolicy(limit=5, window_seconds=3600),
        REFRESH_SCOPE: RatePolicy(limit=20, window_seconds=60),
    }
)


def _digest(kind: str, value: str) -> str:
    return hashlib.sha256(f"{_KEY_DOMAIN}.{kind}:{value}".encode()).hexdigest()


def ip_key(scope: str, ip: str) -> str:
    return f"{scope}:ip:{_digest('ip', ip)}"


def email_key(scope: str, email: str) -> str:
    # Canonical form matches the CITEXT column's case-insensitivity, so
    # Foo@Example.com and foo@example.com share one bucket.
    return f"{scope}:email:{_digest('email', email.strip().lower())}"


def token_key(scope: str, token: str) -> str:
    return f"{scope}:token:{_digest('token', token)}"


def build_auth_charges(
    scope: str, *, ip: str, email: str | None = None, token: str | None = None
) -> tuple[RateCharge, ...]:
    """The one place per-endpoint keys are derived: IP always, subject when given."""
    policy = AUTH_POLICIES[scope]
    charges = [RateCharge(key=ip_key(scope, ip), policy=policy)]
    if email is not None:
        charges.append(RateCharge(key=email_key(scope, email), policy=policy))
    if token is not None:
        charges.append(RateCharge(key=token_key(scope, token), policy=policy))
    return tuple(charges)
