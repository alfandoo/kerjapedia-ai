"""Vector quality: reject the unphysical, verify the index.

Zero/NaN/dimension-violating vectors never reach the store, duplicate
vectors are reported, and an index is only trusted after fresh sample
vectors score cosine >= threshold against its stored ones.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from app.services.rag.embedding.schemas import EmbeddedChunk, VectorIssue


def check_vector(
    item: EmbeddedChunk, dimensions: int
) -> list[VectorIssue]:
    """Reject zero, non-finite, or misdimensioned vectors."""
    issues = []
    if len(item.vector) != dimensions:
        issues.append(
            VectorIssue(
                chunk_id=item.chunk_id,
                code="wrong_dimension",
                message=f"got {len(item.vector)}, expected {dimensions}",
            )
        )
        return issues
    if any(not math.isfinite(value) for value in item.vector):
        issues.append(VectorIssue(chunk_id=item.chunk_id, code="non_finite"))
    norm = math.sqrt(sum(value * value for value in item.vector))
    if norm == 0.0:
        issues.append(VectorIssue(chunk_id=item.chunk_id, code="zero_vector"))
    return issues


def duplicate_vector_groups(items: list[EmbeddedChunk]) -> list[list[str]]:
    """Chunk IDs sharing bit-identical vectors (rounded to 6dp)."""
    by_vector: dict[tuple[float, ...], list[str]] = {}
    for item in items:
        key = tuple(round(value, 6) for value in item.vector)
        by_vector.setdefault(key, []).append(item.chunk_id)
    return [sorted(ids) for ids in by_vector.values() if len(ids) > 1]


def norm_stats(items: list[EmbeddedChunk]) -> dict[str, float]:
    """Mean/min/max L2 norms for the build report."""
    norms = [math.sqrt(sum(v * v for v in item.vector)) for item in items]
    if not norms:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "count": 0}
    return {
        "mean": sum(norms) / len(norms),
        "min": min(norms),
        "max": max(norms),
        "count": len(norms),
    }


def verify_index_compatibility(
    stored: list[list[float]],
    fresh: list[list[float]],
    *,
    min_cosine: float = 0.99,
) -> tuple[bool, float]:
    """Worst-case cosine between stored and freshly embedded samples.

    Returns (compatible, worst_cosine). Below threshold, the index was
    built by another model/revision — refuse to use it.
    """
    worst = 1.0
    for stored_vector, fresh_vector in zip(stored, fresh, strict=False):
        dot = sum(a * b for a, b in zip(stored_vector, fresh_vector, strict=True))
        stored_norm = math.sqrt(sum(a * a for a in stored_vector)) or 1.0
        fresh_norm = math.sqrt(sum(b * b for b in fresh_vector)) or 1.0
        worst = min(worst, dot / (stored_norm * fresh_norm))
    if not stored:
        return False, 0.0
    return worst >= min_cosine, round(worst, 4)


def with_retries(
    action: Callable[[], object],
    *,
    attempts: int = 3,
    sleep: Callable[[float], None] | None = None,
    base_delay_seconds: float = 1.0,
) -> object:
    """Retry a network provider call with exponential backoff."""
    import time

    pause = sleep or time.sleep
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return action()
        except Exception as exc:  # Network providers fail transiently.
            last_error = exc
            if attempt < attempts - 1:
                pause(base_delay_seconds * (2**attempt))
    assert last_error is not None
    raise last_error
