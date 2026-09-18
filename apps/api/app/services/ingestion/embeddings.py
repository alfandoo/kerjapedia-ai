"""Local embedding helpers for the artifact (development) pipeline.

Production retrieval uses Upstash hosted embeddings (raw text in, vectors
out server-side), so no provider here contacts any embedding API. The only
provider is the deterministic hash fallback used by local artifact
ingestion and the offline retrieval engine. Dense/sparse retrieval quality
for production comes from Upstash, not from this module.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.services.ingestion.builds import MAX_EMBEDDING_BATCH_SIZE
from app.services.ingestion.retry import RetryPolicy, run_with_retry, run_with_timeout


class EmbeddingProvider(Protocol):
    model_name: str
    model_revision: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per text."""


@dataclass(frozen=True)
class HybridEmbeddingBatch:
    dense: list[list[float]]
    sparse: list[dict[int, float]]


@dataclass(frozen=True)
class ReliableEmbeddingBatch:
    vectors: HybridEmbeddingBatch
    attempts: int
    duration_seconds: float


class EmbeddingBatchError(RuntimeError):
    def __init__(
        self,
        chunk_ids: list[str],
        *,
        attempts: int,
        cause: Exception,
        duration_seconds: float = 0.0,
    ) -> None:
        self.failed_item_ids = tuple(chunk_ids)
        self.attempts = attempts
        self.cause_type = type(cause).__name__
        self.duration_seconds = duration_seconds
        super().__init__(
            f"Embedding failed for {len(chunk_ids)} chunk(s) after {attempts} "
            f"attempt(s): {self.cause_type}"
        )


_SPARSE_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
# Stopwords carry no legal signal yet would consume L2 mass in the sparse
# channel. Short tokens stay: two-letter legal abbreviations ("pp", "uu",
# "jp", "k3") and digits ("Pasal 15") are first-class sparse terms; only
# single characters are noise.
_SPARSE_STOPWORDS = frozenset(
    {
        "adalah",
        "atau",
        "dan",
        "dari",
        "dengan",
        "di",
        "ini",
        "itu",
        "ke",
        "pada",
        "yang",
        "untuk",
        "baik",
        "bila",
        "karena",
        "maupun",
        "sebagaimana",
        "sebesar",
        "serta",
        "apakah",
        "apa",
        "bagaimana",
        "berapa",
        "kapan",
        "siapa",
        "mengapa",
        "kenapa",
        "atas",
        "dalam",
        "oleh",
        "sebagai",
        "sudah",
        "telah",
        "bahwa",
        "antara",
        "hingga",
        "sampai",
        "saat",
        "ketika",
        "juga",
        "setiap",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
    }
)


def lexical_sparse_vector(text: str) -> dict[int, float]:
    counts = Counter(
        token
        for token in _SPARSE_TOKEN_RE.findall(text.lower())
        if len(token) > 1 and token not in _SPARSE_STOPWORDS
    )
    weighted: dict[int, float] = {}
    for token, count in counts.items():
        index = int.from_bytes(
            hashlib.sha256(token.encode("utf-8")).digest()[:4], "big"
        )
        weighted[index] = 1.0 + math.log1p(count)
    norm = math.sqrt(sum(value * value for value in weighted.values())) or 1.0
    return {index: value / norm for index, value in weighted.items()}


def embed_hybrid(provider: EmbeddingProvider, texts: list[str]) -> HybridEmbeddingBatch:
    """Embed passages (indexing side): no query instruction is applied."""
    method = getattr(provider, "embed_hybrid", None)
    if callable(method):
        return method(texts)
    return HybridEmbeddingBatch(
        dense=provider.embed(texts),
        sparse=[lexical_sparse_vector(text) for text in texts],
    )


def embed_queries_hybrid(
    provider: EmbeddingProvider, texts: list[str]
) -> HybridEmbeddingBatch:
    """Embed queries (retrieval side): same operating point as passages."""
    method = getattr(provider, "embed_queries_hybrid", None)
    if callable(method):
        return method(texts)
    return embed_hybrid(provider, texts)


def embed_hybrid_batched(
    provider: EmbeddingProvider,
    texts: list[str],
    *,
    batch_size: int = 16,
    on_batch: Callable[[int, HybridEmbeddingBatch], None] | None = None,
) -> HybridEmbeddingBatch:
    if batch_size < 1:
        raise ValueError("embedding batch_size must be positive")
    dense: list[list[float]] = []
    sparse: list[dict[int, float]] = []
    for start in range(0, len(texts), batch_size):
        batch = embed_hybrid(provider, texts[start : start + batch_size])
        dense.extend(batch.dense)
        sparse.extend(batch.sparse)
        if on_batch is not None:
            on_batch(start, batch)
    return HybridEmbeddingBatch(dense=dense, sparse=sparse)


def embed_batch_reliably(
    provider: EmbeddingProvider,
    chunk_ids: list[str],
    texts: list[str],
    *,
    expected_dimension: int,
    require_sparse: bool,
    timeout_seconds: float,
    retry_policy: RetryPolicy,
    sleep: Callable[[float], None] = time.sleep,
) -> ReliableEmbeddingBatch:
    """Embed one ordered batch with bounded retries and strict validation."""
    if not chunk_ids or len(chunk_ids) != len(texts):
        raise ValueError("chunk_ids and texts must be non-empty and have equal length")
    if len(chunk_ids) > MAX_EMBEDDING_BATCH_SIZE:
        raise ValueError(
            f"Embedding batch exceeds the maximum of {MAX_EMBEDDING_BATCH_SIZE} items"
        )
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Embedding batch contains duplicate chunk IDs")
    attempts = 1
    started = time.monotonic()

    def on_retry(attempt: int, _delay: float, _exc: Exception) -> None:
        nonlocal attempts
        attempts = attempt + 1

    def operation() -> HybridEmbeddingBatch:
        batch = run_with_timeout(
            lambda: embed_hybrid(provider, texts),
            timeout_seconds,
        )
        validate_embedding_batch(
            batch,
            chunk_ids,
            expected_dimension=expected_dimension,
            require_sparse=require_sparse,
        )
        return batch

    try:
        vectors = run_with_retry(
            operation,
            policy=retry_policy,
            on_retry=on_retry,
            sleep=sleep,
        )
    except Exception as exc:
        raise EmbeddingBatchError(
            chunk_ids,
            attempts=attempts,
            cause=exc,
            duration_seconds=round(time.monotonic() - started, 6),
        ) from exc
    return ReliableEmbeddingBatch(
        vectors=vectors,
        attempts=attempts,
        duration_seconds=round(time.monotonic() - started, 6),
    )


def validate_embedding_batch(
    batch: HybridEmbeddingBatch,
    chunk_ids: list[str],
    *,
    expected_dimension: int,
    require_sparse: bool,
) -> None:
    if len(batch.dense) != len(chunk_ids) or len(batch.sparse) != len(chunk_ids):
        raise ValueError(
            "Embedding provider result count does not match the ordered chunk batch"
        )
    for chunk_id, vector, sparse in zip(
        chunk_ids,
        batch.dense,
        batch.sparse,
        strict=True,
    ):
        if len(vector) != expected_dimension:
            raise ValueError(
                f"Embedding {chunk_id} has {len(vector)} dimensions; "
                f"expected {expected_dimension}"
            )
        if not vector or any(not math.isfinite(float(value)) for value in vector):
            raise ValueError(f"Embedding {chunk_id} contains non-finite values")
        if not any(float(value) != 0.0 for value in vector):
            raise ValueError(f"Embedding {chunk_id} is a zero vector")
        if require_sparse and not sparse:
            raise ValueError(f"Embedding {chunk_id} is missing its sparse vector")
        if any(
            int(index) < 0 or not math.isfinite(float(value))
            for index, value in sparse.items()
        ):
            raise ValueError(f"Embedding {chunk_id} has an invalid sparse vector")


class HashEmbeddingProvider:
    model_name = "local-hash-embedding-v1"
    model_revision = "deterministic-v1"

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            seed = int.from_bytes(
                hashlib.sha256(text.encode("utf-8")).digest()[:8], "big"
            )
            randomizer = random.Random(seed)
            vector = [randomizer.uniform(-1.0, 1.0) for _ in range(self.dimensions)]
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([round(value / norm, 8) for value in vector])
        return vectors


def build_embedding_provider(
    provider_name: str,
    dimensions: int = 64,
) -> EmbeddingProvider:
    """Build a local embedding provider.

    Only ``hash`` remains: production embeddings are hosted by Upstash and
    the self-hosted (BGE-M3) and inference-API providers were retired with
    the Pinecone pipeline. Unknown names raise an actionable error naming
    the supported value.
    """
    if provider_name == "hash":
        return HashEmbeddingProvider(dimensions=dimensions)
    raise ValueError(
        f"Unsupported embedding provider: {provider_name!r}. "
        "Only 'hash' is supported; production embeddings are hosted by Upstash."
    )
