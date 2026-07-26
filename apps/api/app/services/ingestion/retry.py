from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0


def run_with_retry[T](
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    on_retry: Callable[[int, float, Exception], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Retry transient ingestion failures using bounded exponential backoff."""
    attempt = 0
    while True:
        try:
            return operation()
        except Exception as exc:
            if attempt >= policy.max_retries or not is_transient_error(exc):
                raise
            attempt += 1
            delay = min(
                policy.initial_delay_seconds * (2 ** (attempt - 1)),
                policy.max_delay_seconds,
            )
            if on_retry is not None:
                on_retry(attempt, delay, exc)
            sleep(delay)


def is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status_code == 429 or isinstance(status_code, int) and status_code >= 500:
        return True
    name = type(exc).__name__.lower()
    return any(
        marker in name
        for marker in (
            "connection",
            "ratelimit",
            "serviceunavailable",
            "timeout",
        )
    )
