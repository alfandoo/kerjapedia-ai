from app.services.rate_limit import (
    MemoryRateLimitStore,
    RateLimiter,
    client_identity,
    client_ip,
)


def test_identity_prefers_guest_then_token_then_ip() -> None:
    headers = {"x-kerjapedia-guest-id": "abc", "authorization": "Bearer x"}
    assert client_identity(headers, "1.2.3.4", False) == "guest:abc"
    assert client_identity({"authorization": "Bearer x"}, "1.2.3.4", False).startswith("token:")
    assert client_identity({}, "1.2.3.4", False) == "ip:1.2.3.4"


def test_proxy_header_ignored_unless_trusted() -> None:
    headers = {"x-forwarded-for": "9.9.9.9, 1.2.3.4"}

    assert client_ip(headers, "1.2.3.4", False) == "1.2.3.4"
    assert client_ip(headers, "1.2.3.4", True) == "9.9.9.9"
    assert client_identity(headers, "1.2.3.4", True) == "ip:9.9.9.9"


def test_identity_budget_blocks_before_ip_ceiling() -> None:
    limiter = RateLimiter(2, redis_url="")

    assert limiter.backend == "memory"
    assert limiter.check("guest:a", "1.1.1.1").allowed is True
    assert limiter.check("guest:a", "1.1.1.1").allowed is True
    denied = limiter.check("guest:a", "1.1.1.1")
    assert denied.allowed is False
    assert denied.retry_after_seconds == 60
    # Another identity on the same IP still has budget.
    assert limiter.check("guest:b", "1.1.1.1").allowed is True


def test_ip_ceiling_catches_identifier_rotation() -> None:
    limiter = RateLimiter(100, redis_url="", ip_ceiling_multiplier=1)

    for index in range(100):
        assert limiter.check(f"guest:rot-{index}", "9.9.9.9").allowed is True
    denied = limiter.check("guest:rot-new", "9.9.9.9")
    assert denied.allowed is False


def test_redis_backend_counts_across_instances() -> None:
    import app.services.rate_limit as rate_limit_module

    real_store = rate_limit_module.RedisRateLimitStore
    backing: dict[str, int] = {}

    class FakeStore:
        def increment(self, key, window_seconds, now):
            backing[key] = backing.get(key, 0) + 1
            return backing[key]

    try:
        rate_limit_module.RedisRateLimitStore = lambda url: FakeStore()
        limiter = RateLimiter(1, redis_url="redis://test")
        assert limiter.backend == "redis"
        assert limiter.check("guest:a", "1.1.1.1").allowed is True
        assert limiter.check("guest:a", "1.1.1.1").allowed is False
    finally:
        rate_limit_module.RedisRateLimitStore = real_store


def test_memory_store_windows_reset() -> None:
    store = MemoryRateLimitStore()

    assert store.increment("k", 60, now=1000.0) == 1
    assert store.increment("k", 60, now=1001.0) == 2
    assert store.increment("k", 60, now=2000.0) == 1
