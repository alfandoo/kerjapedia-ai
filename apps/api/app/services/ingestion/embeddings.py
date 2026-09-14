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

from openai import OpenAI

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


def lexical_sparse_vector(text: str) -> dict[int, float]:
    counts = Counter(_SPARSE_TOKEN_RE.findall(text.lower()))
    weighted: dict[int, float] = {}
    for token, count in counts.items():
        index = int.from_bytes(
            hashlib.sha256(token.encode("utf-8")).digest()[:4], "big"
        )
        weighted[index] = 1.0 + math.log1p(count)
    norm = math.sqrt(sum(value * value for value in weighted.values())) or 1.0
    return {index: value / norm for index, value in weighted.items()}


def embed_hybrid(provider: EmbeddingProvider, texts: list[str]) -> HybridEmbeddingBatch:
    method = getattr(provider, "embed_hybrid", None)
    if callable(method):
        return method(texts)
    return HybridEmbeddingBatch(
        dense=provider.embed(texts),
        sparse=[lexical_sparse_vector(text) for text in texts],
    )


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


class BGEM3EmbeddingProvider:
    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        dimensions: int = 1024,
        require_native_sparse: bool = False,
        model_revision: str = "unversioned",
        batch_size: int = 16,
    ) -> None:
        self.model_name = model_name
        self.model_revision = model_revision
        self.dimensions = dimensions
        self.require_native_sparse = require_native_sparse
        self.batch_size = batch_size
        self.sparse_fallback_used = False
        self._model = None
        self._hybrid_model = None
        self._resolved_model_path: str | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for EMBEDDING_PROVIDER=bge_m3."
                ) from exc
            self._model = SentenceTransformer(self._model_path())

        encoded = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=self.batch_size,
        )
        vectors = [list(map(float, vector)) for vector in encoded]
        self._validate_dimensions(vectors)
        return vectors

    def embed_hybrid(self, texts: list[str]) -> HybridEmbeddingBatch:
        if self._hybrid_model is None:
            try:
                from FlagEmbedding import BGEM3FlagModel
            except ImportError as exc:
                if self.require_native_sparse:
                    raise RuntimeError(
                        "FlagEmbedding is required for BGE-M3 dense+sparse retrieval."
                    ) from exc
                self.sparse_fallback_used = True
                return HybridEmbeddingBatch(
                    dense=self.embed(texts),
                    sparse=[lexical_sparse_vector(text) for text in texts],
                )
            self._hybrid_model = BGEM3FlagModel(
                self._model_path(),
                use_fp16=False,
                batch_size=self.batch_size,
                passage_max_length=550,
                query_max_length=512,
            )
        encoded = self._hybrid_model.encode(
            texts,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
            batch_size=self.batch_size,
        )
        dense: list[list[float]] = []
        for raw_vector in encoded["dense_vecs"]:
            vector = list(map(float, raw_vector))
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            dense.append([value / norm for value in vector])
        self._validate_dimensions(dense)
        sparse = [
            {int(index): float(value) for index, value in weights.items()}
            for weights in encoded["lexical_weights"]
        ]
        if self.require_native_sparse and any(not weights for weights in sparse):
            raise RuntimeError("BGE-M3 returned an empty native sparse vector.")
        return HybridEmbeddingBatch(dense=dense, sparse=sparse)

    def _model_path(self) -> str:
        if self.model_revision in {"", "main", "unversioned", "provider-managed"}:
            return self.model_name
        if self._resolved_model_path is None:
            try:
                from huggingface_hub import snapshot_download
            except ImportError as exc:
                raise RuntimeError(
                    "huggingface-hub is required to pin BGE-M3 revisions."
                ) from exc
            self._resolved_model_path = snapshot_download(
                repo_id=self.model_name,
                revision=self.model_revision,
            )
        return self._resolved_model_path

    def _validate_dimensions(self, vectors: list[list[float]]) -> None:
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise RuntimeError(
                    f"{self.model_name} returned {len(vector)} dimensions; "
                    f"expected {self.dimensions}."
                )


class OpenAIEmbeddingProvider:
    model_revision = "provider-managed"

    def __init__(
        self,
        api_key: str,
        model_name: str,
        dimensions: int,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model_name = model_name
        self.dimensions = dimensions
        self.client = OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model_name,
            input=texts,
            dimensions=self.dimensions,
        )
        ordered = sorted(response.data, key=lambda item: int(item.index))
        return [item.embedding for item in ordered]


def build_embedding_provider(
    provider_name: str,
    model_name: str = "BAAI/bge-m3",
    dimensions: int = 1024,
    openai_api_key: str | None = None,
    require_native_sparse: bool = False,
    model_revision: str = "unversioned",
    batch_size: int = 16,
    timeout_seconds: float = 120.0,
) -> EmbeddingProvider:
    if provider_name == "bge_m3":
        return BGEM3EmbeddingProvider(
            model_name=model_name,
            dimensions=dimensions,
            require_native_sparse=require_native_sparse,
            model_revision=model_revision,
            batch_size=batch_size,
        )
    if provider_name == "hash":
        return HashEmbeddingProvider(dimensions=dimensions)
    if provider_name == "openai":
        if not openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for EMBEDDING_PROVIDER=openai."
            )
        return OpenAIEmbeddingProvider(
            api_key=openai_api_key,
            model_name=model_name or "text-embedding-3-small",
            dimensions=dimensions,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"Unsupported embedding provider: {provider_name}")
