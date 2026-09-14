from __future__ import annotations

import hashlib
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

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
from app.services.ingestion.schemas import Chunk, DocumentMetadata, EmbeddedChunk
from app.services.ingestion.vector_indexing import (
    VectorIndexConfig,
    VectorIndexingError,
    expected_vector_metadata,
    index_document_reliably,
    validate_chunks_for_index,
    verify_indexed_vectors,
)
from app.services.retrieval.pinecone_store import PineconeConfig, PineconeRetrievalStore


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


class FakeVectorStore:
    def __init__(self, *, transient_failures: int = 0) -> None:
        self.transient_failures = transient_failures
        self.upsert_calls = 0
        self.clear_calls = 0
        self.vectors: dict[str, dict] = {}

    def clear_namespace(self) -> None:
        self.clear_calls += 1
        self.vectors.clear()

    def upsert_document(
        self,
        document: DocumentMetadata,
        version: int,
        embedded_chunks: list[EmbeddedChunk],
        batch_size: int = 100,
        publication_status: str = "draft",
        source_verification_status: str | None = None,
        legal_review_status: str = "pending",
        is_current: bool = True,
        replace_document: bool = True,
    ) -> int:
        del (
            version,
            batch_size,
            publication_status,
            source_verification_status,
            legal_review_status,
            is_current,
            replace_document,
        )
        self.upsert_calls += 1
        if self.upsert_calls <= self.transient_failures:
            raise ConnectionError("temporary vector service failure")
        for item in embedded_chunks:
            self.vectors[item.chunk.chunk_id] = expected_vector_metadata(document, item)
        return len(embedded_chunks)

    def fetch_vector_metadata(self, vector_ids: list[str]) -> dict[str, dict]:
        return {
            vector_id: self.vectors[vector_id]
            for vector_id in vector_ids
            if vector_id in self.vectors
        }

    def namespace_vector_count(self) -> int:
        return len(self.vectors)


def sample_document() -> DocumentMetadata:
    return DocumentMetadata(
        document_id="PP-35-2021",
        title="Peraturan Pemerintah Nomor 35 Tahun 2021",
        short_title="PP 35/2021",
        regulation_type="PP",
        number=35,
        year=2021,
        issuer="Pemerintah Republik Indonesia",
        topics=["pkwt"],
        legal_status="active",
        source_name="JDIH BPK",
        source_url="https://peraturan.bpk.go.id/",
        local_file="dataset/PP-35-2021.pdf",
        file_name="PP-35-2021.pdf",
        size_bytes=100,
        sha256="a" * 64,
        verification_status="verified",
    )


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


def sample_embedded(chunk_id: str = "chunk-1") -> EmbeddedChunk:
    chunk = sample_chunk(chunk_id)
    retrieval_text = chunk.retrieval_text or chunk.text
    return EmbeddedChunk(
        chunk=chunk,
        embedding_model="test-embedding",
        embedding=[1.0, 0.5, 0.25],
        sparse_embedding={1: 1.0},
        embedding_revision="revision-1",
        retrieval_text_sha256=hashlib.sha256(retrieval_text.encode()).hexdigest(),
    )


def vector_config(**overrides) -> VectorIndexConfig:
    return VectorIndexConfig(
        batch_size=overrides.get("batch_size", 2),
        timeout_seconds=overrides.get("timeout_seconds", 1.0),
        max_retries=overrides.get("max_retries", 2),
        retry_initial_seconds=overrides.get("retry_initial_seconds", 0.25),
        verification_attempts=overrides.get("verification_attempts", 1),
    )


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
        lambda: VectorIndexConfig(batch_size=101),
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


def test_vector_index_retries_batches_and_is_idempotent() -> None:
    store = FakeVectorStore(transient_failures=1)
    document = sample_document()
    chunks = [sample_embedded(f"chunk-{index}") for index in range(3)]
    delays: list[float] = []

    first = index_document_reliably(
        store,
        document,
        1,
        chunks,
        expected_model="test-embedding",
        expected_revision="revision-1",
        expected_dimension=3,
        config=vector_config(),
        publication_status="published",
        source_verification_status="verified",
        legal_review_status="verified",
        is_current=True,
        sleep=delays.append,
    )
    second = index_document_reliably(
        store,
        document,
        1,
        chunks,
        expected_model="test-embedding",
        expected_revision="revision-1",
        expected_dimension=3,
        config=vector_config(),
        publication_status="published",
        source_verification_status="verified",
        legal_review_status="verified",
        is_current=True,
        sleep=lambda _delay: None,
    )

    assert first.indexed_chunks == 3
    assert first.batches == 2
    assert first.retries == 1
    assert delays == [0.25]
    assert second.indexed_chunks == 3
    assert len(store.vectors) == 3


def test_vector_validation_happens_before_any_write() -> None:
    store = FakeVectorStore()
    invalid = replace(sample_embedded(), embedding=[1.0, 0.5])

    with pytest.raises(VectorIndexingError) as error:
        index_document_reliably(
            store,
            sample_document(),
            1,
            [invalid],
            expected_model="test-embedding",
            expected_revision="revision-1",
            expected_dimension=3,
            config=vector_config(),
            publication_status="published",
            source_verification_status="verified",
            legal_review_status="verified",
            is_current=True,
        )

    assert error.value.failed_item_ids == ("chunk-1",)
    assert store.upsert_calls == 0


def test_vector_write_failure_reports_batch_ids_after_bounded_retries() -> None:
    store = FakeVectorStore(transient_failures=10)
    chunks = [sample_embedded("chunk-1"), sample_embedded("chunk-2")]
    delays: list[float] = []

    with pytest.raises(VectorIndexingError) as error:
        index_document_reliably(
            store,
            sample_document(),
            1,
            chunks,
            expected_model="test-embedding",
            expected_revision="revision-1",
            expected_dimension=3,
            config=vector_config(max_retries=2),
            publication_status="published",
            source_verification_status="verified",
            legal_review_status="verified",
            is_current=True,
            sleep=delays.append,
        )

    assert store.upsert_calls == 3
    assert delays == [0.25, 0.5]
    assert error.value.failed_item_ids == ("chunk-1", "chunk-2")
    assert error.value.cause_type == "ConnectionError"


def test_vector_metadata_validation_rejects_content_drift() -> None:
    item = sample_embedded()
    invalid = replace(item, retrieval_text_sha256="0" * 64)

    with pytest.raises(VectorIndexingError, match="content provenance"):
        validate_chunks_for_index(
            sample_document(),
            [invalid],
            expected_model="test-embedding",
            expected_revision="revision-1",
            expected_dimension=3,
        )


def test_vector_verification_requires_exact_ids_metadata_and_count() -> None:
    store = FakeVectorStore()
    document = sample_document()
    item = sample_embedded()
    expected = {item.chunk.chunk_id: expected_vector_metadata(document, item)}
    store.vectors[item.chunk.chunk_id] = dict(expected[item.chunk.chunk_id])

    verify_indexed_vectors(store, expected, config=vector_config())

    store.vectors["unexpected"] = {"chunk_id": "unexpected"}
    with pytest.raises(VectorIndexingError, match="expected=1, indexed=2"):
        verify_indexed_vectors(store, expected, config=vector_config())

    del store.vectors["unexpected"]
    store.vectors[item.chunk.chunk_id]["embedding_revision"] = "wrong"
    with pytest.raises(VectorIndexingError) as error:
        verify_indexed_vectors(store, expected, config=vector_config())
    assert error.value.failed_item_ids == (item.chunk.chunk_id,)


def test_pinecone_adapter_exposes_exact_metadata_and_namespace_count() -> None:
    class FakeIndex:
        def fetch(self, *, ids: list[str], namespace: str):
            assert ids == ["chunk-1"]
            assert namespace == "release-test"
            return SimpleNamespace(
                vectors={
                    "chunk-1": SimpleNamespace(
                        metadata={"chunk_id": "chunk-1", "build_id": "ingb_test"}
                    )
                }
            )

        def describe_index_stats(self):
            return SimpleNamespace(
                namespaces={"release-test": SimpleNamespace(vector_count=1)}
            )

    store = PineconeRetrievalStore(
        PineconeConfig(
            api_key="test",
            namespace="release-test",
            dimension=3,
        ),
        FlakyEmbeddingProvider(),
    )
    store._index = FakeIndex()

    assert store.fetch_vector_metadata(["chunk-1"]) == {
        "chunk-1": {"chunk_id": "chunk-1", "build_id": "ingb_test"}
    }
    assert store.namespace_vector_count() == 1


def test_pinecone_adapter_rejects_partial_upsert_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeIndex:
        def upsert(self, *, vectors: list[dict], namespace: str):
            assert len(vectors) == 1
            assert namespace == "release-test"
            return SimpleNamespace(upserted_count=0)

    store = PineconeRetrievalStore(
        PineconeConfig(
            api_key="test",
            namespace="release-test",
            dimension=3,
        ),
        FlakyEmbeddingProvider(),
    )
    store._index = FakeIndex()
    monkeypatch.setattr(store, "ensure_index", lambda: None)

    with pytest.raises(RuntimeError, match="acknowledge every vector"):
        store.upsert_document(
            sample_document(),
            1,
            [sample_embedded()],
            replace_document=False,
        )


def test_pinecone_adapter_rejects_empty_replacement_before_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test", dimension=3),
        FlakyEmbeddingProvider(),
    )
    monkeypatch.setattr(
        store,
        "ensure_index",
        lambda: pytest.fail("empty payload must fail before touching Pinecone"),
    )

    with pytest.raises(ValueError, match="at least one"):
        store.upsert_document(sample_document(), 1, [])
