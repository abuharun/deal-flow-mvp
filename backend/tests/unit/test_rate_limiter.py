"""Bounded in-memory rate limiter and auth policies (Task B5, slice B3).

Contracts under test:
- RateLimiter is an async, concurrency-safe sliding-window counter with an
  injectable monotonic clock and no background task. A hit checks EVERY key
  first and only then charges them all, so a request rejected by any key
  consumes nothing on the others (documented multi-key contract).
- RateLimitExceeded always carries a positive integer retry_after bounded by
  the policy window.
- The key table is bounded: expired keys are pruned deterministically before
  the oldest live key is evicted, and the table never exceeds max_keys.
- Keys are opaque `scope:kind:sha256hex` strings — domain-separated SHA-256
  over canonicalized input (emails lowercased/stripped), never Python hash()
  and never the raw email/token/IP value.
- The auth policies are frozen module constants with the agreed limits.
"""

import asyncio
import dataclasses
import re

import pytest

from app.security.rate_limit import (
    ACTIVATE_INVITE_SCOPE,
    AUTH_POLICIES,
    FORGOT_PASSWORD_SCOPE,
    LOGIN_SCOPE,
    REFRESH_SCOPE,
    RESET_PASSWORD_SCOPE,
    VERIFY_EMAIL_SCOPE,
    RateCharge,
    RateLimiter,
    RateLimitExceeded,
    RatePolicy,
    build_auth_charges,
    email_key,
    ip_key,
    token_key,
)

KEY_SHAPE = re.compile(r"^[a-z_.]+:(ip|email|token):[0-9a-f]{64}$")


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock()


def limiter_with(clock, max_keys: int = 10_000) -> RateLimiter:
    return RateLimiter(max_keys=max_keys, clock=clock)


def charge(key: str, limit: int = 5, window: float = 60.0) -> RateCharge:
    return RateCharge(key=key, policy=RatePolicy(limit=limit, window_seconds=window))


class TestSingleKeyWindow:
    async def test_allows_exactly_limit_hits_then_rejects(self, clock):
        limiter = limiter_with(clock)
        for _ in range(5):
            await limiter.hit([charge("k", limit=5)])
        with pytest.raises(RateLimitExceeded):
            await limiter.hit([charge("k", limit=5)])

    async def test_retry_after_is_a_positive_bounded_int(self, clock):
        limiter = limiter_with(clock)
        await limiter.hit([charge("k", limit=1, window=60)])
        with pytest.raises(RateLimitExceeded) as excinfo:
            await limiter.hit([charge("k", limit=1, window=60)])
        retry_after = excinfo.value.retry_after
        assert isinstance(retry_after, int)
        assert 1 <= retry_after <= 60

    async def test_retry_after_is_the_ceiling_of_the_remaining_window(self, clock):
        limiter = limiter_with(clock)
        await limiter.hit([charge("k", limit=1, window=60)])
        clock.advance(30.5)
        with pytest.raises(RateLimitExceeded) as excinfo:
            await limiter.hit([charge("k", limit=1, window=60)])
        assert excinfo.value.retry_after == 30

    async def test_retry_after_never_rounds_down_to_zero(self, clock):
        limiter = limiter_with(clock)
        await limiter.hit([charge("k", limit=1, window=60)])
        clock.advance(59.9)
        with pytest.raises(RateLimitExceeded) as excinfo:
            await limiter.hit([charge("k", limit=1, window=60)])
        assert excinfo.value.retry_after == 1

    async def test_window_slides_and_frees_capacity(self, clock):
        limiter = limiter_with(clock)
        await limiter.hit([charge("k", limit=2, window=60)])
        clock.advance(10)
        await limiter.hit([charge("k", limit=2, window=60)])
        with pytest.raises(RateLimitExceeded):
            await limiter.hit([charge("k", limit=2, window=60)])
        clock.advance(51)  # t=61: only the t=0 hit has expired
        await limiter.hit([charge("k", limit=2, window=60)])
        with pytest.raises(RateLimitExceeded):
            await limiter.hit([charge("k", limit=2, window=60)])

    async def test_rejected_hit_consumes_nothing(self, clock):
        limiter = limiter_with(clock)
        await limiter.hit([charge("k", limit=2, window=60)])
        clock.advance(10)
        await limiter.hit([charge("k", limit=2, window=60)])
        clock.advance(10)
        with pytest.raises(RateLimitExceeded):
            await limiter.hit([charge("k", limit=2, window=60)])
        # t=61: the t=0 hit expired. Had the rejected t=20 attempt been
        # charged, hits at t=10 and t=20 would still fill the window.
        clock.advance(41)
        await limiter.hit([charge("k", limit=2, window=60)])


class TestMultiKeyAtomicity:
    async def test_rejection_by_one_key_charges_no_other_key(self, clock):
        limiter = limiter_with(clock)
        for _ in range(5):
            await limiter.hit([charge("b", limit=5)])
        with pytest.raises(RateLimitExceeded):
            await limiter.hit([charge("a", limit=5), charge("b", limit=5)])
        # `a` must still have its full budget: the rejected combined hit
        # consumed nothing (documented contract).
        for _ in range(5):
            await limiter.hit([charge("a", limit=5)])
        with pytest.raises(RateLimitExceeded):
            await limiter.hit([charge("a", limit=5)])

    async def test_success_charges_every_key(self, clock):
        limiter = limiter_with(clock)
        for _ in range(3):
            await limiter.hit([charge("a", limit=3), charge("b", limit=5)])
        with pytest.raises(RateLimitExceeded):
            await limiter.hit([charge("a", limit=3)])
        # b took exactly the 3 combined charges.
        for _ in range(2):
            await limiter.hit([charge("b", limit=5)])
        with pytest.raises(RateLimitExceeded):
            await limiter.hit([charge("b", limit=5)])

    async def test_concurrent_multi_key_hits_cannot_exceed_the_limit(self, clock):
        limiter = limiter_with(clock)

        async def one() -> bool:
            try:
                await limiter.hit([charge("a", limit=10), charge("b", limit=10)])
                return True
            except RateLimitExceeded:
                return False

        results = await asyncio.gather(*(one() for _ in range(30)))
        assert results.count(True) == 10


class TestConcurrency:
    async def test_concurrent_hits_admit_exactly_the_limit(self, clock):
        limiter = limiter_with(clock)

        async def one() -> bool:
            try:
                await limiter.hit([charge("k", limit=10)])
                return True
            except RateLimitExceeded:
                return False

        results = await asyncio.gather(*(one() for _ in range(50)))
        assert results.count(True) == 10
        assert results.count(False) == 40


class TestBoundedKeys:
    async def test_oldest_key_is_evicted_at_capacity(self, clock):
        limiter = limiter_with(clock, max_keys=3)
        for key in ("k1", "k2", "k3"):
            await limiter.hit([charge(key, limit=1)])
        await limiter.hit([charge("k4", limit=1)])  # evicts k1, the oldest
        await limiter.hit([charge("k1", limit=1)])  # k1 returns as a fresh key
        with pytest.raises(RateLimitExceeded):
            await limiter.hit([charge("k4", limit=1)])  # k4 is still tracked

    async def test_expired_keys_are_pruned_before_live_ones_are_evicted(self, clock):
        limiter = limiter_with(clock, max_keys=3)
        await limiter.hit([charge("old", limit=1, window=60)])
        clock.advance(10)
        await limiter.hit([charge("live1", limit=1, window=60)])
        await limiter.hit([charge("live2", limit=1, window=60)])
        clock.advance(55)  # `old` expired at t=60; live1/live2 still in window
        await limiter.hit([charge("fresh", limit=1, window=60)])
        with pytest.raises(RateLimitExceeded):
            await limiter.hit([charge("live1", limit=1, window=60)])
        with pytest.raises(RateLimitExceeded):
            await limiter.hit([charge("live2", limit=1, window=60)])

    async def test_key_table_never_exceeds_max_keys(self, clock):
        limiter = limiter_with(clock, max_keys=3)
        for index in range(20):
            await limiter.hit([charge(f"k{index}", limit=1)])
        assert limiter.tracked_keys <= 3


class TestKeyDerivation:
    def test_email_key_canonicalizes_case_and_whitespace(self):
        assert email_key(LOGIN_SCOPE, "  Foo@EXAMPLE.com ") == email_key(
            LOGIN_SCOPE, "foo@example.com"
        )

    def test_keys_are_opaque_sha256_shapes_without_raw_values(self):
        for key, raw in (
            (email_key(LOGIN_SCOPE, "foo@example.com"), "foo@example.com"),
            (ip_key(LOGIN_SCOPE, "203.0.113.9"), "203.0.113.9"),
            (token_key(RESET_PASSWORD_SCOPE, "raw-reset-token"), "raw-reset-token"),
        ):
            assert KEY_SHAPE.fullmatch(key), key
            assert raw not in key

    def test_key_kinds_are_domain_separated(self):
        value = "identical-input"
        keys = {
            email_key(LOGIN_SCOPE, value),
            ip_key(LOGIN_SCOPE, value),
            token_key(LOGIN_SCOPE, value),
        }
        assert len(keys) == 3

    def test_scopes_are_separated(self):
        assert email_key(LOGIN_SCOPE, "a@example.com") != email_key(
            FORGOT_PASSWORD_SCOPE, "a@example.com"
        )

    def test_build_auth_charges_shares_one_policy_per_scope(self):
        charges = build_auth_charges(LOGIN_SCOPE, ip="203.0.113.9", email="a@example.com")
        assert [c.policy for c in charges] == [AUTH_POLICIES[LOGIN_SCOPE]] * 2
        assert charges[0].key == ip_key(LOGIN_SCOPE, "203.0.113.9")
        assert charges[1].key == email_key(LOGIN_SCOPE, "a@example.com")

    def test_build_auth_charges_with_token(self):
        charges = build_auth_charges(RESET_PASSWORD_SCOPE, ip="203.0.113.9", token="tok")
        assert [c.key for c in charges] == [
            ip_key(RESET_PASSWORD_SCOPE, "203.0.113.9"),
            token_key(RESET_PASSWORD_SCOPE, "tok"),
        ]

    def test_build_auth_charges_ip_only(self):
        charges = build_auth_charges(REFRESH_SCOPE, ip="203.0.113.9")
        assert [c.key for c in charges] == [ip_key(REFRESH_SCOPE, "203.0.113.9")]


class TestFrozenPolicies:
    def test_agreed_auth_policy_values(self):
        assert AUTH_POLICIES[LOGIN_SCOPE] == RatePolicy(limit=5, window_seconds=60)
        assert AUTH_POLICIES[FORGOT_PASSWORD_SCOPE] == RatePolicy(limit=3, window_seconds=3600)
        assert AUTH_POLICIES[ACTIVATE_INVITE_SCOPE] == RatePolicy(limit=10, window_seconds=3600)
        assert AUTH_POLICIES[VERIFY_EMAIL_SCOPE] == RatePolicy(limit=10, window_seconds=3600)
        assert AUTH_POLICIES[RESET_PASSWORD_SCOPE] == RatePolicy(limit=5, window_seconds=3600)
        assert AUTH_POLICIES[REFRESH_SCOPE] == RatePolicy(limit=20, window_seconds=60)

    def test_policies_are_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            AUTH_POLICIES[LOGIN_SCOPE].limit = 1000  # type: ignore[misc]
        with pytest.raises(TypeError):
            AUTH_POLICIES[LOGIN_SCOPE] = RatePolicy(limit=1000, window_seconds=1)  # type: ignore[index]
