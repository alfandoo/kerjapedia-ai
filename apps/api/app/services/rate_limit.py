"""Two-tier rate limiting: per-identity budget plus a coarser IP ceiling.

Identity resolves to a guest UUID, a login-session hash, or the client
IP — in that order. The IP ceiling survives identifier rotation; the
identity budget survives NAT sharing (notably the Next.js BFF proxy,
where every browser looks like one TCP peer). Counts live in Redis when
reachable and fall back to process memory otherwise.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger("kerjapedia.api")

GUEST_HEADER = "x-kerjapedia-guest-id"
_FORWARDED_HEADER = "x-forwarded-for"


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0
    identity: str = ""
    backend: str = "memory"


def client_ip(headers: dict, peer_ip: str, trust_proxy: bool) -> str:
    """Client IP honoring X-Forwarded-For only behind a trusted proxy.

    Untrusted proxy headers are attacker-controlled, so they must never
    feed budgeting decisions by default.
    """
    if trust_proxy:
        forwarded = headers.get(_FORWARDED_HEADER, "")
        first = (forwarded.split(",")[0] if forwarded else "").strip()
        if first:
            return first
    return peer_ip or "unknown"


def client_identity(headers: dict, peer_ip: str, trust_proxy: bool) -> str:
    """Stable budgeting identity: guest UUID, session hash, else IP."""
    guest_id = (headers.get(GUEST_HEADER, "") or "").strip()
    if guest_id:
        return f"guest:{guest_id}"
    authorization = (headers.get("authorization", "") or "").strip()
    if authorization:
        digest = hashlib.sha256(authorization.encode("utf-8")).hexdigest()[:16]
        return f"token:{digest}"
    return f"ip:{client_ip(headers, peer_ip, trust_proxy)}"


class MemoryRateLimitStore:
    """Process-local fixed-window counters (fallback, not multi-replica)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[int, float]] = {}

    def increment(self, key: str, window_seconds: int, now: float) -> int:
        with self._lock:
            count, started_at = self._counts.get(key, (0, now))
            if now - started_at >= window_seconds:
                count, started_at = 0, now
            count += 1
            self._counts[key] = (count, started_at)
            return count


class RedisRateLimitStore:
    """Fixed-window counters in Redis shared across replicas."""

    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, socket_timeout=0.5)

    def increment(self, key: str, window_seconds: int, now: float) -> int:
        _ = now
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        count, _ = pipe.execute()
        return int(count)


class RateLimiter:
    """Identity budget plus IP ceiling, Redis-first with memory fallback."""

    def __init__(
        self,
        limit_per_minute: int,
        *,
        redis_url: str = "",
        ip_ceiling_multiplier: int = 10,
        window_seconds: int = 60,
    ) -> None:
        self._limit = limit_per_minute
        self._ip_limit = limit_per_minute * ip_ceiling_multiplier
        self._window = window_seconds
        self._memory = MemoryRateLimitStore()
        self._redis = None
        if redis_url:
            try:
                self._redis = RedisRateLimitStore(redis_url)
            except Exception as exc:
                logger.warning("rate limiter Redis unavailable, using memory: %s", exc)

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def _increment(self, key: str) -> tuple[int, str]:
        now = time.time()
        namespaced = f"ratelimit:{key}"
        if self._redis is not None:
            try:
                return self._redis.increment(namespaced, self._window, now), "redis"
            except Exception as exc:
                logger.warning("rate limiter Redis failed, using memory: %s", exc)
                self._redis = None
        return self._memory.increment(namespaced, self._window, now), "memory"

    def check(self, identity: str, ip: str) -> RateLimitDecision:
        """Deny when either tier is exhausted; identity tier first."""
        identity_count, backend = self._increment(f"id:{identity}")
        if identity_count > self._limit:
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=self._window,
                identity=identity,
                backend=backend,
            )
        ip_count, backend = self._increment(f"ip:{ip}")
        if ip_count > self._ip_limit:
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=self._window,
                identity=identity,
                backend=backend,
            )
        return RateLimitDecision(allowed=True, identity=identity, backend=backend)
