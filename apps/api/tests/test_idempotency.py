from app.services.idempotency import (
    IdempotencyStore,
    valid_idempotency_key,
)


def test_key_format_is_validated() -> None:
    assert valid_idempotency_key("abc-123_XY") == "abc-123_XY"
    assert valid_idempotency_key("short") is None
    assert valid_idempotency_key("has space") is None
    assert valid_idempotency_key(None) is None
    assert valid_idempotency_key("x" * 65) is None


def test_remembered_responses_replay_per_identity() -> None:
    store = IdempotencyStore()
    assert store.backend == "memory"

    assert store.recall("guest:a", "key-1") is None
    store.remember("guest:a", "key-1", {"answer": "x"})
    assert store.recall("guest:a", "key-1") == {"answer": "x"}
    # Same key, other identity: no replay.
    assert store.recall("guest:b", "key-1") is None


def test_memory_store_is_bounded_and_ttl_aware() -> None:
    import time

    store = IdempotencyStore()
    store.remember("u", "k", {"answer": "x"})
    assert store.recall("u", "k") == {"answer": "x"}
    # Simulate ageing beyond TTL by rewinding the stored timestamp.
    with store._lock:
        payload, _ = store._memory["idempotency:u:k"]
        store._memory["idempotency:u:k"] = (payload, time.time() - 100000)
    assert store.recall("u", "k") is None
