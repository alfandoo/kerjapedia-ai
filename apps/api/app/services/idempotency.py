"""Idempotency keys for safe retries: same key + same user replays.

Completed responses are stored under (identity, key) for 24 hours.
Only successful completions are remembered — failures, conflicts, and
rate limits stay retryable. Redis-first with a bounded memory fallback.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import OrderedDict

logger = logging.getLogger("kerjapedia.api")

IDEMPOTENCY_HEADER = "idempotency-key"
_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")
_TTL_SECONDS = 24 * 3600
_MEMORY_CAP = 1000


def valid_idempotency_key(value: str | None) -> str | None:
    """Return the key when well-formed, else None (caller rejects)."""
    if value and _IDEMPOTENCY_KEY_RE.match(value):
        return value
    return None


class IdempotencyStore:
    """Completed-response memory keyed by (identity, idempotency key)."""

    def __init__(self, redis_url: str = "") -> None:
        self._redis = None
        if redis_url:
            try:
                import redis

                self._redis = redis.Redis.from_url(redis_url, socket_timeout=0.5)
            except Exception as exc:
                logger.warning("idempotency Redis unavailable, using memory: %s", exc)
        self._lock = threading.Lock()
        self._memory: OrderedDict[str, tuple[str, float]] = OrderedDict()

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def _redis_get(self, key: str) -> str | None:
        try:
            value = self._redis.get(key)
            return value.decode("utf-8") if isinstance(value, bytes) else value
        except Exception as exc:
            logger.warning("idempotency Redis failed, using memory: %s", exc)
            self._redis = None
            return None

    def _redis_set(self, key: str, payload: str) -> None:
        try:
            self._redis.set(key, payload, ex=_TTL_SECONDS)
        except Exception as exc:
            logger.warning("idempotency Redis failed, using memory: %s", exc)
            self._redis = None
            self._memory_set(key, payload)

    def _memory_get(self, key: str) -> str | None:
        with self._lock:
            entry = self._memory.get(key)
            if entry is None:
                return None
            payload, stored_at = entry
            if time.time() - stored_at > _TTL_SECONDS:
                del self._memory[key]
                return None
            self._memory.move_to_end(key)
            return payload

    def _memory_set(self, key: str, payload: str) -> None:
        with self._lock:
            self._memory[key] = (payload, time.time())
            while len(self._memory) > _MEMORY_CAP:
                self._memory.popitem(last=False)

    def recall(self, identity: str, idempotency_key: str) -> dict | None:
        """Return the stored response, or None on first sight."""
        key = f"idempotency:{identity}:{idempotency_key}"
        if self._redis is not None:
            raw = self._redis_get(key)
            if raw is not None:
                return self._decode(raw)
        raw = self._memory_get(key)
        return self._decode(raw) if raw is not None else None

    @staticmethod
    def _decode(raw: str) -> dict | None:
        try:
            decoded = json.loads(raw)
        except ValueError:
            return None
        return decoded if isinstance(decoded, dict) else None

    def remember(self, identity: str, idempotency_key: str, response: dict) -> None:
        """Store a successful response for later replay."""
        key = f"idempotency:{identity}:{idempotency_key}"
        payload = json.dumps(response, ensure_ascii=False, default=str)
        if self._redis is not None:
            self._redis_set(key, payload)
        else:
            self._memory_set(key, payload)
