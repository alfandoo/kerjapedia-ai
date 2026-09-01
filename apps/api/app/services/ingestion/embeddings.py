from __future__ import annotations

import hashlib
import math
import random
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI


class EmbeddingProvider(Protocol):
    model_name: str
    model_revision: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per text."""


@dataclass(frozen=True)
class HybridEmbeddingBatch:
    dense: list[list[float]]
    sparse: list[dict[int, float]]


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

    def __init__(self, api_key: str, model_name: str) -> None:
        self.model_name = model_name
        self.client = OpenAI(api_key=api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model_name, input=texts)
        return [item.embedding for item in response.data]


def build_embedding_provider(
    provider_name: str,
    model_name: str = "BAAI/bge-m3",
    dimensions: int = 1024,
    openai_api_key: str | None = None,
    require_native_sparse: bool = False,
    model_revision: str = "unversioned",
    batch_size: int = 16,
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
        return HashEmbeddingProvider()
    if provider_name == "openai":
        if not openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for EMBEDDING_PROVIDER=openai."
            )
        return OpenAIEmbeddingProvider(
            api_key=openai_api_key,
            model_name=model_name or "text-embedding-3-small",
        )
    raise ValueError(f"Unsupported embedding provider: {provider_name}")
