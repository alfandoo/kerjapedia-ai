"""Bridge synchronous validation code to cancellable async provider I/O."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import CancelledError as FutureCancelled
from concurrent.futures import Future
from contextvars import ContextVar
from threading import Event, Lock
from typing import Any


class ProviderCancelled(asyncio.CancelledError):
    pass


class ProviderRequestScope:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.cancelled = Event()
        self._lock = Lock()
        self._pending: set[Future[Any]] = set()
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def submit(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        with self._lock:
            if self.cancelled.is_set():
                coroutine.close()
                raise ProviderCancelled()
            future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
            self._pending.add(future)
        try:
            result = future.result()
            usage = getattr(result, "usage", None)
            with self._lock:
                self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
                self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
            if self.cancelled.is_set():
                raise ProviderCancelled()
            return result
        except FutureCancelled as exc:
            raise ProviderCancelled() from exc
        finally:
            with self._lock:
                self._pending.discard(future)

    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        with self._lock:
            self.prompt_tokens += max(0, prompt_tokens)
            self.completion_tokens += max(0, completion_tokens)

    def cancel(self) -> None:
        with self._lock:
            self.cancelled.set()
            pending = tuple(self._pending)
        for future in pending:
            future.cancel()

    @property
    def usage(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }

current_provider_scope: ContextVar[ProviderRequestScope | None] = ContextVar(
    "current_provider_scope", default=None
)
