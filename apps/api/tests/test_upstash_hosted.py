"""Upstash hosted-embedding migration tests (Upstash API is mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.ingestion.upstash_indexing import (
    transform_chunk,
    validate_chunks,
)
from app.services.retrieval.upstash_vector_store import (
    UpstashVectorConfig,
    UpstashVectorStore,
    build_upstash_filter,
)


def make_store(**overrides) -> UpstashVectorStore:
    config = UpstashVectorConfig(url="https://example.upstash.io", token="test-token")
    kwargs = {"config": config}
    kwargs.update(overrides)
    return UpstashVectorStore(**kwargs)


class FakeIndex:
    def __init__(self) -> None:
        self.upsert_calls: list[dict] = []
        self.query_calls: list[dict] = []
        self.info_payload = SimpleNamespace(
            vector_count=10,
            dimension=1536,
            similarity_function="COSINE",
            dense_index=SimpleNamespace(
                dimension=1536,
                similarity_function="COSINE",
                embedding_model="open-ai/text-embedding-3-small",
            ),
            sparse_index=SimpleNamespace(embedding_model="BM25"),
            namespaces={},
        )

    def upsert(self, vectors, namespace=""):
        self.upsert_calls.append({"vectors": list(vectors), "namespace": namespace})
        return "ok"

    def query(
        self,
        vector=None,
        top_k=10,
        include_vectors=False,
        include_metadata=False,
        filter="",
        data=None,
        namespace="",
        include_data=False,
        sparse_vector=None,
        weighting_strategy=None,
        fusion_algorithm=None,
        query_mode=None,
    ):
        self.query_calls.append(
            {
                "vector": vector,
                "data": data,
                "top_k": top_k,
                "filter": filter,
                "namespace": namespace,
                "query_mode": query_mode,
                "sparse_vector": sparse_vector,
            }
        )
        return []

    def info(self):
        return self.info_payload

    def fetch(
        self,
        ids=None,
        include_vectors=False,
        include_metadata=False,
        namespace="",
        include_data=False,
        prefix=None,
    ):
        return [
            SimpleNamespace(metadata={"chunk_id": vector_id, "document_id": "PP-35-2021"})
            for vector_id in (ids or [])
        ]

    def delete_namespace(self, namespace):
        return None


def sample_record() -> dict:
    return {
        "chunk_id": "PP-35-2021-abc123",
        "document_id": "PP-35-2021",
        "content": "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
        "content_hash": "x",
        "page_start": 12,
        "page_end": 12,
        "token_count": 9,
        "source": "Database Peraturan JDIH BPK",
        "source_url": "https://peraturan.bpk.go.id/",
        "metadata": {
            "document": {
                "document_id": "PP-35-2021",
                "document_type": "PP",
                "document_number": 35,
                "year": 2021,
                "document_title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
                "regulation_status": "active",
                "source_url": "https://peraturan.bpk.go.id/",
            },
            "structure": {
                "bab": "BAB II",
                "bagian": "PKWT",
                "pasal": "Pasal 15",
                "ayat": "Ayat (1)",
            },
            "chunk": {"chunk_index": 3},
        },
    }


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
def test_rest_env_aliases_populate_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTASH_VECTOR_REST_URL", "https://rest.example.upstash.io")
    monkeypatch.setenv("UPSTASH_VECTOR_REST_TOKEN", "rest-token")
    parsed = Settings()
    assert parsed.upstash_vector_url == "https://rest.example.upstash.io"
    assert parsed.upstash_vector_token == "rest-token"


def test_legacy_env_names_still_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTASH_VECTOR_URL", "https://legacy.example.upstash.io")
    monkeypatch.setenv("UPSTASH_VECTOR_TOKEN", "legacy-token")
    parsed = Settings()
    assert parsed.upstash_vector_url == "https://legacy.example.upstash.io"
    assert parsed.upstash_vector_token == "legacy-token"


# ----------------------------------------------------------------------
# Chunk validation / transformation
# ----------------------------------------------------------------------
def test_validate_rejects_empty_text_and_duplicates() -> None:
    good = sample_record()
    empty = {**sample_record(), "chunk_id": "empty-1", "content": "   "}
    dupe = {**sample_record()}
    valid, report = validate_chunks([good, empty, dupe], verify_content_hash=False)
    assert [item["chunk_id"] for item in valid] == ["PP-35-2021-abc123"]
    assert report.total == 3
    assert report.valid == 1
    assert report.skipped == 2
    assert report.skipped_reasons["empty_text"] == 1
    assert report.skipped_reasons["duplicate_id"] == 1


def test_validate_detects_content_hash_mismatch() -> None:
    record = {**sample_record(), "content_hash": "deadbeef"}
    valid, report = validate_chunks([record], verify_content_hash=True)
    assert valid == []
    assert report.skipped_reasons["content_hash_mismatch"] == 1


def test_transform_preserves_id_text_and_metadata() -> None:
    record = transform_chunk(sample_record())
    assert record["chunk_id"] == "PP-35-2021-abc123"
    assert record["text"] == sample_record()["content"]
    metadata = record["metadata"]
    assert metadata["document_id"] == "PP-35-2021"
    assert metadata["title"] == "Peraturan Pemerintah Nomor 35 Tahun 2021"
    assert metadata["year"] == 2021
    assert metadata["page_start"] == 12
    assert metadata["chunk_index"] == 3
    assert metadata["article"] == "Pasal 15"
    assert metadata["source_url"] == "https://peraturan.bpk.go.id/"
    assert metadata["embedding_model"] == "upstash-hosted:text-embedding-3-small"
    # Flat and serializable: no nested dicts.
    json.dumps(metadata)
    assert not any(isinstance(value, dict) for value in metadata.values())


def test_transform_does_not_fabricate_metadata() -> None:
    minimal = {"chunk_id": "X-1", "content": "some text", "metadata": {}}
    record = transform_chunk(minimal)
    assert "category" not in record["metadata"]
    assert "language" not in record["metadata"]


# ----------------------------------------------------------------------
# Hosted-embedding store behaviour (mocked index)
# ----------------------------------------------------------------------
def test_upsert_sends_raw_data_not_vectors() -> None:
    store = make_store()
    fake = FakeIndex()
    store._index = fake  # type: ignore[attr-defined]
    record = transform_chunk(sample_record())
    assert store.upsert_chunks([record]) == 1
    (call,) = fake.upsert_calls
    (vector,) = call["vectors"]
    assert vector.id == "PP-35-2021-abc123"
    assert vector.data == sample_record()["content"]
    assert vector.vector is None
    assert vector.sparse_vector is None
    assert call["namespace"] == "production"


def test_query_sends_raw_text_in_hybrid_mode() -> None:
    from upstash_vector.types import QueryMode

    store = make_store()
    fake = FakeIndex()
    store._index = fake  # type: ignore[attr-defined]
    store.query("Apakah pekerja PKWT memperoleh kompensasi?", top_k=20)
    (call,) = fake.query_calls
    assert call["data"] == "Apakah pekerja PKWT memperoleh kompensasi?"
    assert call["vector"] is None
    assert call["sparse_vector"] is None
    assert call["query_mode"] == QueryMode.HYBRID
    assert call["top_k"] == 20


def test_verify_index_accepts_expected_configuration() -> None:
    store = make_store()
    store._index = FakeIndex()  # type: ignore[attr-defined]
    report = store.verify_index(strict=True)
    assert report.matches_expected
    assert report.problems == ()


def test_verify_index_rejects_wrong_configuration() -> None:
    store = make_store()
    fake = FakeIndex()
    fake.info_payload.dense_index.embedding_model = "custom-embedding-v9"
    store._index = fake  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="hosted-embedding contract"):
        store.verify_index(strict=True)


def test_search_normalizes_results_and_preserves_metadata() -> None:
    store = make_store()
    fake = FakeIndex()
    record = transform_chunk(sample_record())

    def fake_query(**kwargs):
        fake.query_calls.append(kwargs)
        return [
            {
                "id": record["chunk_id"],
                "score": 0.92,
                "metadata": record["metadata"],
                "data": record["text"],
            }
        ]

    fake.query = fake_query  # type: ignore[method-assign]
    store._index = fake  # type: ignore[attr-defined]
    response = store.search("Apakah pekerja PKWT memperoleh kompensasi?", top_k=5)
    assert not response.should_refuse
    (ranked,) = response.results
    assert ranked.document.chunk_id == "PP-35-2021-abc123"
    assert ranked.document.document_id == "PP-35-2021"
    assert ranked.document.article == "Pasal 15"
    assert ranked.document.page_start == 12
    assert "kompensasi" in ranked.document.text
    # Raw text reached the (mocked) hybrid endpoint; no local embedding ran.
    assert fake.query_calls
    assert all(call.get("vector") is None for call in fake.query_calls)


def test_search_governance_drops_unpublished_when_disallowed() -> None:
    store = make_store(allow_unpublished=False)
    fake = FakeIndex()
    record = transform_chunk(sample_record())
    record["metadata"]["publication_status"] = "draft"

    def fake_query(**kwargs):
        return [
            {
                "id": record["chunk_id"],
                "score": 0.9,
                "metadata": record["metadata"],
                "data": record["text"],
            }
        ]

    fake.query = fake_query  # type: ignore[method-assign]
    store._index = fake  # type: ignore[attr-defined]
    response = store.search("Apakah pekerja PKWT memperoleh kompensasi?", top_k=5)
    assert response.should_refuse


# ----------------------------------------------------------------------
# Filter builder
# ----------------------------------------------------------------------
def test_build_upstash_filter_scalars_only() -> None:
    assert (
        build_upstash_filter({"year": 2021, "article": "Pasal 15"})
        == "article = 'Pasal 15' AND year = 2021"
    )
    assert build_upstash_filter({"topics": ["pkwt"], "year": None}) == ""
    assert build_upstash_filter(None) == ""


def test_build_upstash_filter_rejects_unsafe_identifier() -> None:
    with pytest.raises(ValueError, match="Unsafe filter field"):
        build_upstash_filter({"year; DROP": 2021})


# ----------------------------------------------------------------------
# Active path must not embed locally
# ----------------------------------------------------------------------
def test_active_store_has_no_local_embedding_hooks() -> None:
    source = Path("app/services/retrieval/upstash_vector_store.py").read_text(encoding="utf-8")
    assert "SentenceTransformer" not in source
    assert "from openai" not in source
    assert "import pinecone" not in source
    assert "_embed_query" not in source
    assert "_bm25" not in source
    assert "PineconeInference" not in source
    store = make_store()
    assert not hasattr(store, "_embed_query")
    assert not hasattr(store, "_pinecone_client")
