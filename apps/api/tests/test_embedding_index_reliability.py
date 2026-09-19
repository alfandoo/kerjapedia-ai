from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

from app.services.ingestion.artifacts import ArtifactStore
from app.services.ingestion.builds import IngestionBuildConfig
from app.services.ingestion.embeddings import (
    EmbeddingBatchError,
    HybridEmbeddingBatch,
    embed_batch_reliably,
)
from app.services.ingestion.pipeline import _embed_chunks_with_checkpoint
from app.services.ingestion.retry import RetryPolicy
from app.services.ingestion.schemas import Chunk


def sample_chunk(chunk_id: str = "chunk-1") -> Chunk:
    retrieval_text = "PP 35/2021\nPasal 15\n(1) Pengusaha memberikan kompensasi."
    artifact_checksum = hashlib.sha256(
        f"{chunk_id}\n{retrieval_text}".encode()
    ).hexdigest()
    return Chunk(
        chunk_id=chunk_id,
        document_id="PP-35-2021",
        chapter="BAB III",
        section="Bagian Kesatu",
        article="Pasal 15",
        paragraph="Ayat (1)",
        page_start=12,
        page_end=13,
        text="Pasal 15\n(1) Pengusaha memberikan kompensasi.",
        token_count=8,
        topics=["pkwt"],
        legal_status="active",
        source_url="https://peraturan.bpk.go.id/",
        build_id="ingb_test",
        retrieval_text=retrieval_text,
        artifact_checksum=artifact_checksum,
    )


class FlakyEmbeddingProvider:
    model_name = "test-embedding"
    model_revision = "revision-1"
    dimensions = 3

    def __init__(self, failures: int = 0, *, dimensions: int = 3) -> None:
        self.failures = failures
        self.dimensions = dimensions
        self.calls = 0

    def embed_hybrid(self, texts: list[str]) -> HybridEmbeddingBatch:
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("temporary provider timeout")
        return HybridEmbeddingBatch(
            dense=[
                [float(index + 1), 0.5, 0.25][: self.dimensions]
                for index, _ in enumerate(texts)
            ],
            sparse=[{index + 1: 1.0} for index, _ in enumerate(texts)],
        )


class SlowEmbeddingProvider(FlakyEmbeddingProvider):
    def embed_hybrid(self, texts: list[str]) -> HybridEmbeddingBatch:
        time.sleep(0.05)
        return super().embed_hybrid(texts)


class FailIfCalledProvider(FlakyEmbeddingProvider):
    def embed_hybrid(self, texts: list[str]) -> HybridEmbeddingBatch:
        raise AssertionError("valid checkpoint should have been reused")


def test_embedding_retries_transient_failures_with_exponential_backoff() -> None:
    provider = FlakyEmbeddingProvider(failures=2)
    delays: list[float] = []

    result = embed_batch_reliably(
        provider,
        ["chunk-1", "chunk-2"],
        ["satu", "dua"],
        expected_dimension=3,
        require_sparse=True,
        timeout_seconds=1,
        retry_policy=RetryPolicy(max_retries=2, initial_delay_seconds=0.25),
        sleep=delays.append,
    )

    assert result.attempts == 3
    assert provider.calls == 3
    assert delays == [0.25, 0.5]
    assert result.vectors.dense[0] == [1.0, 0.5, 0.25]
    assert result.vectors.dense[1] == [2.0, 0.5, 0.25]


def test_embedding_dimension_failure_reports_every_ordered_item() -> None:
    provider = FlakyEmbeddingProvider(dimensions=2)

    with pytest.raises(EmbeddingBatchError) as error:
        embed_batch_reliably(
            provider,
            ["chunk-1", "chunk-2"],
            ["satu", "dua"],
            expected_dimension=3,
            require_sparse=True,
            timeout_seconds=1,
            retry_policy=RetryPolicy(max_retries=3, initial_delay_seconds=0),
            sleep=lambda _delay: None,
        )

    assert error.value.failed_item_ids == ("chunk-1", "chunk-2")
    assert error.value.attempts == 1
    assert error.value.cause_type == "ValueError"


def test_embedding_timeout_is_bounded_and_reported() -> None:
    with pytest.raises(EmbeddingBatchError) as error:
        embed_batch_reliably(
            SlowEmbeddingProvider(),
            ["chunk-1"],
            ["satu"],
            expected_dimension=3,
            require_sparse=True,
            timeout_seconds=0.001,
            retry_policy=RetryPolicy(max_retries=0),
        )

    assert error.value.failed_item_ids == ("chunk-1",)
    assert error.value.cause_type == "TimeoutError"


def test_embedding_checkpoint_reuses_valid_vectors(tmp_path: Path) -> None:
    config = IngestionBuildConfig(
        embedding_model="test-embedding",
        embedding_revision="revision-1",
        embedding_dimension=3,
        require_native_sparse=True,
        embedding_batch_size=1,
        runtime={},
    )
    store = ArtifactStore(tmp_path)
    chunks = [sample_chunk()]
    first = _embed_chunks_with_checkpoint(
        store,
        Path("documents/test/build"),
        chunks,
        FlakyEmbeddingProvider(),
        config,
        resume=True,
    )
    second = _embed_chunks_with_checkpoint(
        store,
        Path("documents/test/build"),
        chunks,
        FailIfCalledProvider(),
        config,
        resume=True,
    )

    assert first.batches == 1
    assert first.reused_chunks == 0
    assert second.batches == 0
    assert second.reused_chunks == 1
    assert second.embedded_chunks == first.embedded_chunks


@pytest.mark.parametrize(
    "config",
    [
        lambda: IngestionBuildConfig(embedding_batch_size=65),
    ],
)
def test_batch_sizes_are_bounded(config) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        config()


def test_embedding_service_rejects_an_oversized_direct_batch() -> None:
    with pytest.raises(ValueError, match="exceeds the maximum"):
        embed_batch_reliably(
            FlakyEmbeddingProvider(),
            [f"chunk-{index}" for index in range(65)],
            ["text"] * 65,
            expected_dimension=3,
            require_sparse=True,
            timeout_seconds=1,
            retry_policy=RetryPolicy(),
        )
