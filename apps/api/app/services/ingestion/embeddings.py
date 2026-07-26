from __future__ import annotations

import hashlib
import math
import random
from typing import Protocol

from openai import OpenAI


class EmbeddingProvider(Protocol):
    model_name: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per text."""


class HashEmbeddingProvider:
    model_name = "local-hash-embedding-v1"

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
            randomizer = random.Random(seed)
            vector = [randomizer.uniform(-1.0, 1.0) for _ in range(self.dimensions)]
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([round(value / norm, 8) for value in vector])
        return vectors


class BGEM3EmbeddingProvider:
    def __init__(self, model_name: str = "BAAI/bge-m3", dimensions: int = 1024) -> None:
        self.model_name = model_name
        self.dimensions = dimensions
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for EMBEDDING_PROVIDER=bge_m3."
                ) from exc
            self._model = SentenceTransformer(self.model_name)

        encoded = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = [list(map(float, vector)) for vector in encoded]
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise RuntimeError(
                    f"{self.model_name} returned {len(vector)} dimensions; "
                    f"expected {self.dimensions}."
                )
        return vectors


class OpenAIEmbeddingProvider:
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
) -> EmbeddingProvider:
    if provider_name == "bge_m3":
        return BGEM3EmbeddingProvider(model_name=model_name, dimensions=dimensions)
    if provider_name == "hash":
        return HashEmbeddingProvider()
    if provider_name == "openai":
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for EMBEDDING_PROVIDER=openai.")
        return OpenAIEmbeddingProvider(
            api_key=openai_api_key,
            model_name=model_name or "text-embedding-3-small",
        )
    raise ValueError(f"Unsupported embedding provider: {provider_name}")
