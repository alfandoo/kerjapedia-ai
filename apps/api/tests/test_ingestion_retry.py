from __future__ import annotations

import pytest

from app.services.ingestion.retry import RetryPolicy, run_with_retry


def test_retry_recovers_from_transient_failure() -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("provider timeout")
        return "completed"

    result = run_with_retry(
        operation,
        policy=RetryPolicy(max_retries=2, initial_delay_seconds=0.5),
        sleep=delays.append,
    )

    assert result == "completed"
    assert attempts == 3
    assert delays == [0.5, 1.0]


def test_retry_does_not_repeat_permanent_failure() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid metadata")

    with pytest.raises(ValueError, match="invalid metadata"):
        run_with_retry(
            operation,
            policy=RetryPolicy(max_retries=3),
            sleep=lambda _: None,
        )

    assert attempts == 1


def test_retry_stops_at_configured_limit() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise ConnectionError("pinecone unavailable")

    with pytest.raises(ConnectionError):
        run_with_retry(
            operation,
            policy=RetryPolicy(max_retries=2),
            sleep=lambda _: None,
        )

    assert attempts == 3
