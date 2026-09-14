from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from queue import Queue
from threading import Thread
from typing import Any


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if self.initial_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays must not be negative")


def run_with_timeout[T](operation: Callable[[], T], timeout_seconds: float) -> T:
    """Bound a blocking provider call without swallowing its exception."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    outcome: Queue[tuple[bool, Any]] = Queue(maxsize=1)

    def invoke() -> None:
        try:
            outcome.put((True, operation()))
        except BaseException as exc:
            outcome.put((False, exc))

    worker = Thread(target=invoke, daemon=True, name="ingestion-provider-call")
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        raise TimeoutError(
            f"Provider operation exceeded {timeout_seconds:g} seconds"
        )
    succeeded, value = outcome.get_nowait()
    if succeeded:
        return value
    if isinstance(value, BaseException):
        raise value
    raise RuntimeError("Provider operation returned an invalid outcome")


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
