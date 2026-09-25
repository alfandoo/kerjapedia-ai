"""Vector store interface plus an in-memory backend.

Production access is Upstash Vector HYBRID (dense text-embedding-3-small +
BM25); every guard below runs against the interface, so rules are
backend-independent and fully testable. The ``pinecone_*`` parameter names
below are historic aliases kept for backward compatibility — they refer to
the generic ``vector_filter``.
"""

from __future__ import annotations

import math
from typing import Protocol


class VectorStore(Protocol):
    """Minimal surface every backend must honor."""

    def upsert(self, vectors: list, namespace: str) -> int: ...

    def fetch(self, ids: list[str], namespace: str) -> dict: ...

    def delete_ids(self, ids: list[str], namespace: str) -> int: ...

    def delete_by_filter(
        self, vector_filter: dict | None = None, namespace: str = "", **kwargs
    ) -> int: ...

    def count(self, namespace: str) -> int: ...

    def sample_ids(self, namespace: str, limit: int) -> list[str]: ...

    def query(
        self,
        vector: list[float],
        top_k: int,
        namespace: str,
        vector_filter: dict | None = None,
        **kwargs,
    ) -> list[tuple[str, float]]: ...


def _cosine(left: list[float] | tuple[float, ...], right: list[float] | tuple[float, ...]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return dot / (left_norm * right_norm)


class InMemoryVectorStore:
    """Exact, inspectable backend for tests and offline validation."""

    def __init__(self) -> None:
        self._vectors: dict[tuple[str, str], object] = {}

    def upsert(self, vectors: list, namespace: str) -> int:
        for vector in vectors:
            self._vectors[(namespace, vector.id)] = vector
        return len(vectors)

    def fetch(self, ids: list[str], namespace: str) -> dict:
        return {
            chunk_id: self._vectors[(namespace, chunk_id)]
            for chunk_id in ids
            if (namespace, chunk_id) in self._vectors
        }

    def delete_ids(self, ids: list[str], namespace: str) -> int:
        removed = 0
        for chunk_id in ids:
            if self._vectors.pop((namespace, chunk_id), None) is not None:
                removed += 1
        return removed

    def delete_by_filter(
        self,
        vector_filter: dict | None = None,
        namespace: str = "",
        pinecone_filter: dict | None = None,
        **_kwargs,
    ) -> int:
        active_filter = vector_filter if vector_filter is not None else pinecone_filter
        matched = [
            key for key, vector in self._vectors.items()
            if key[0] == namespace and _matches(vector.metadata, active_filter)
        ]
        for key in matched:
            del self._vectors[key]
        return len(matched)

    def count(self, namespace: str) -> int:
        return sum(1 for (space, _) in self._vectors if space == namespace)

    def sample_ids(self, namespace: str, limit: int) -> list[str]:
        return [chunk_id for (space, chunk_id) in self._vectors if space == namespace][:limit]

    def query(
        self,
        vector: list[float],
        top_k: int,
        namespace: str,
        vector_filter: dict | None = None,
        pinecone_filter: dict | None = None,
        **_kwargs,
    ) -> list[tuple[str, float]]:
        active_filter = vector_filter if vector_filter is not None else pinecone_filter
        scored = [
            (chunk_id, _cosine(vector, item.values))
            for (space, chunk_id), item in self._vectors.items()
            if space == namespace and _matches(item.metadata, active_filter)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]


def _matches(metadata: dict, vector_filter: dict | None = None, **kwargs) -> bool:
    # Backward-compatible alias: ``pinecone_filter=`` still accepted.
    if vector_filter is None and "pinecone_filter" in kwargs:
        vector_filter = kwargs["pinecone_filter"]
    if not vector_filter:
        return True
    for key, condition in vector_filter.items():
        value = metadata.get(key)
        if isinstance(condition, dict):
            if "$eq" in condition and value != condition["$eq"]:
                return False
            if "$in" in condition and value not in condition["$in"]:
                return False
            if "$gte" in condition and not (value is not None and value >= condition["$gte"]):
                return False
            if "$lte" in condition and not (value is not None and value <= condition["$lte"]):
                return False
        elif value != condition:
            return False
    return True
