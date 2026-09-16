"""Embedding providers with honest sparse provenance.

- ``HashEmbeddingProvider`` is quarantined: constructing it for any
  purpose but ``"test"`` raises, so random vectors can never again
  reach a real index unnoticed.
- ``BGEM3Provider`` serves dense vectors via sentence-transformers and
  native sparse vectors via FlagEmbedding when present; otherwise it
  falls back to lexical sparsity and says so in ``sparse_kind``.
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


class BGEM3Provider:
    """BGE-M3 dense vectors; native sparse when FlagEmbedding is present."""

    def __init__(self, config: EmbeddingConfig) -> None:
        resolved = effective_config(config)
        self.model_name = resolved.model_name
        self.model_revision = resolved.model_revision
        self.dimensions = resolved.dimensions
        self.batch_size = resolved.batch_size
        self.require_native_sparse = resolved.require_native_sparse
        self._model = None
        self._hybrid_model = None
        self._resolved_path: str | None = None
        self._sparse_kind = "native"

    @property
    def sparse_kind(self) -> str:
        return self._sparse_kind

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for BGE-M3."
                ) from exc
            self._model = SentenceTransformer(self._model_path())
        encoded = self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False,
            batch_size=self.batch_size,
        )
        vectors = [list(map(float, vector)) for vector in encoded]
        self._check_dimensions(vectors)
        return vectors

    def embed_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        native = self._native_sparse(texts)
        if native is not None:
            self._sparse_kind = "native"
            return native
        self._sparse_kind = "lexical"
        return [lexical_sparse_vector(text) for text in texts]

    def _native_sparse(self, texts: list[str]) -> list[dict[int, float]] | None:
        if self._hybrid_model is None:
            try:
                from FlagEmbedding import BGEM3FlagModel
            except ImportError:
                if self.require_native_sparse:
                    raise RuntimeError(
                        "FlagEmbedding is required for native BGE-M3 sparsity."
                    ) from None
                return None
            self._hybrid_model = BGEM3FlagModel(
                self._model_path(), use_fp16=False, batch_size=self.batch_size
            )
        encoded = self._hybrid_model.encode(
            texts, return_dense=False, return_sparse=True,
            return_colbert_vecs=False, batch_size=self.batch_size,
        )
        sparse = [
            {int(index): float(value) for index, value in weights.items()}
            for weights in encoded["lexical_weights"]
        ]
        if self.require_native_sparse and any(not weights for weights in sparse):
            raise RuntimeError("BGE-M3 returned an empty native sparse vector.")
        return sparse

    def _model_path(self) -> str:
        if self.model_revision in {"", "main", "unversioned"}:
            return self.model_name
        if self._resolved_path is None:
            try:
                from huggingface_hub import snapshot_download
            except ImportError as exc:
                raise RuntimeError(
                    "huggingface-hub is required to pin BGE-M3 revisions."
                ) from exc
            self._resolved_path = snapshot_download(
                repo_id=self.model_name, revision=self.model_revision
            )
        return self._resolved_path

    def _check_dimensions(self, vectors: list[list[float]]) -> None:
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise RuntimeError(
                    f"{self.model_name} returned {len(vector)} dimensions; "
                    f"expected {self.dimensions}."
                )
