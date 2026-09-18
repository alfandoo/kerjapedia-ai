"""Embedding providers with honest sparse provenance.

- ``HashEmbeddingProvider`` is quarantined: constructing it for any
  purpose but ``"test"`` raises, so random vectors can never again
  reach a real index unnoticed.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections import Counter
from typing import Protocol

from app.services.rag.embedding.schemas import EmbeddingConfig

_SPARSE_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
# Mirrors the live ingestion fallback: stopwords consume sparse L2 mass
# without legal signal; short legal tokens and digits stay. Keep both
# implementations in sync — sparse index spaces must match exactly.
_SPARSE_STOPWORDS = frozenset(
    {
        "adalah", "atau", "dan", "dari", "dengan", "di", "ini", "itu",
        "ke", "pada", "yang", "untuk", "baik", "bila", "karena",
        "maupun", "sebagaimana", "sebesar", "serta", "apakah", "apa",
        "bagaimana", "berapa", "kapan", "siapa", "mengapa", "kenapa",
        "atas", "dalam", "oleh", "sebagai", "sudah", "telah", "bahwa",
        "antara", "hingga", "sampai", "saat", "ketika", "juga",
        "setiap", "the", "and", "or", "of", "to", "in",
    }
)


class EmbeddingProvider(Protocol):
    """Dense vectors plus declared sparse provenance."""

    model_name: str
    model_revision: str
    dimensions: int
    sparse_kind: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_sparse(self, texts: list[str]) -> list[dict[int, float]]: ...


def lexical_sparse_vector(text: str) -> dict[int, float]:
    """Deterministic lexical sparsity: token hashes, log weights, unit norm."""
    counts = Counter(
        token
        for token in _SPARSE_TOKEN_RE.findall(text.lower())
        if len(token) > 1 and token not in _SPARSE_STOPWORDS
    )
    weighted: dict[int, float] = {}
    for token, count in counts.items():
        index = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big")
        weighted[index] = 1.0 + math.log1p(count)
    norm = math.sqrt(sum(value * value for value in weighted.values())) or 1.0
    return {index: value / norm for index, value in weighted.items()}


def effective_config(config: EmbeddingConfig) -> EmbeddingConfig:
    """Refuse unpinned revisions unless explicitly allowed for experiments."""
    from dataclasses import replace

    if not config.model_revision and not config.allow_unpinned_revision:
        raise ValueError(
            "model_revision must be pinned (or allow_unpinned_revision=True "
            "for throwaway experiments)."
        )
    return replace(config)


class HashEmbeddingProvider:
    """Deterministic random vectors. Tests only — by construction."""

    model_revision = "deterministic-v1"
    sparse_kind = "none"

    def __init__(self, dimensions: int = 64, purpose: str = "test") -> None:
        if purpose != "test":
            raise ValueError(
                f"HashEmbeddingProvider is quarantined for tests; refusing purpose={purpose!r}."
            )
        self.model_name = "local-hash-embedding-v1"
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
            randomizer = random.Random(seed)
            vector = [randomizer.uniform(-1.0, 1.0) for _ in range(self.dimensions)]
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([round(value / norm, 8) for value in vector])
        return vectors

    def embed_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        return [{} for _ in texts]


