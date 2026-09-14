"""Write guards: verify after writing, bound sizes, delete carefully.

- Verified writes read back samples and compare cosine plus identity;
  a mismatch rolls the batch back instead of publishing corruption.
- Metadata is sized before sending; oversized payloads shed bulk in
  priority order (parent context first, then long texts) and say so.
- Namespace deletion previews by default and only destroys on explicit
  confirmation, returning the backed-up ID list.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable

from app.services.rag.indexing.schemas import (
    NamespaceClearance,
    StoredVector,
    WriteReport,
)

METADATA_LIMIT_BYTES = 40960
_VERIFY_SAMPLE = 5

# Bulk shed first on oversize, in this order.
_DROP_ORDER = ("parent_text", "parent_context", "debug")
_TRUNCATABLE = ("text", "retrieval_text", "quote")


def estimate_metadata_size(metadata: dict) -> int:
    """JSON byte size of a metadata payload."""
    return len(json.dumps(metadata, ensure_ascii=False).encode("utf-8"))


def fit_metadata(
    metadata: dict, limit_bytes: int = METADATA_LIMIT_BYTES
) -> tuple[dict, list[str]]:
    """Drop bulk, then truncate long texts, until the payload fits.

    Returns the fitted payload plus the fields that were shed.
    """
    fitted = dict(metadata)
    shed: list[str] = []
    for key in _DROP_ORDER:
        if estimate_metadata_size(fitted) <= limit_bytes:
            break
        if fitted.pop(key, None) is not None:
            shed.append(key)
    for key in _TRUNCATABLE:
        while estimate_metadata_size(fitted) > limit_bytes:
            value = fitted.get(key)
            if not isinstance(value, str) or len(value) <= 100:
                break
            fitted[key] = value[: len(value) // 2]
            if key not in shed:
                shed.append(key)
    return fitted, shed


def write_verified(
    store: object,
    vectors: list[StoredVector],
    namespace: str,
    *,
    min_cosine: float = 0.99,
    sample_size: int = _VERIFY_SAMPLE,
    attempts: int = 3,
    sleep: Callable[[float], None] | None = None,
) -> WriteReport:
    """Upsert, read back samples, roll back the batch on mismatch."""
    pause = sleep or time.sleep
    upserted = store.upsert(vectors, namespace)
    sample_ids = [vector.id for vector in vectors[: max(1, sample_size)]]
    sent = {vector.id: vector for vector in vectors}
    worst = 1.0
    verified = 0
    fetched: dict = {}
    for _ in range(max(1, attempts)):
        fetched = store.fetch(sample_ids, namespace)
        if len(fetched) >= len(sample_ids):
            break
        pause(1.0)
    for chunk_id in sample_ids:
        stored = fetched.get(chunk_id)
        expected = sent[chunk_id]
        if stored is None or getattr(stored, "id", None) != chunk_id:
            return _rollback(store, vectors, namespace)
        cosine = _cosine(list(stored.values), list(expected.values))
        worst = min(worst, cosine)
        if cosine < min_cosine:
            return _rollback(store, vectors, namespace)
        if dict(getattr(stored, "metadata", {}) or {}).get("chunk_id", chunk_id) != chunk_id:
            return _rollback(store, vectors, namespace)
        verified += 1
    return WriteReport(
        upserted=upserted, verified=verified, worst_cosine=round(worst, 4), rolled_back=False
    )


def _rollback(store: object, vectors: list[StoredVector], namespace: str) -> WriteReport:
    store.delete_ids([vector.id for vector in vectors], namespace)
    return WriteReport(upserted=len(vectors), verified=0, worst_cosine=0.0, rolled_back=True)


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return dot / (left_norm * right_norm)


def clear_namespace_guarded(
    store: object, namespace: str, *, confirm: bool = False
) -> NamespaceClearance:
    """Preview without confirmation; destroy with a backup on confirmation."""
    count = store.count(namespace)
    sample = tuple(store.sample_ids(namespace, 5))
    if not confirm:
        return NamespaceClearance(
            namespace=namespace, vector_count=count, sample_ids=sample, confirmed=False
        )
    backed_up = tuple(store.sample_ids(namespace, max(count, 1)))
    store.delete_by_filter(None, namespace)
    return NamespaceClearance(
        namespace=namespace,
        vector_count=count,
        sample_ids=sample,
        backed_up_ids=backed_up,
        confirmed=True,
    )
