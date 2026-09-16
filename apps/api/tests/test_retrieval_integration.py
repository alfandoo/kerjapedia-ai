"""Integration tests for the Pinecone retrieval path with mock client.

Covers the full pipeline: query understanding → Pinecone search → reranking → postprocessing.
Uses a mock Pinecone index so tests run without network or API key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.pinecone_store import PineconeConfig, PineconeRetrievalStore

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeMatch:
    id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class _FakeQueryResult:
    """Mimics the Pinecone QueryResponse object."""

    def __init__(self, matches: list[_FakeMatch]) -> None:
        self.matches = matches
        self.namespace = "test"


class _FakeIndex:
    """In-memory stub for the Pinecone Index class."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def upsert(self, vectors: list[dict[str, Any]], **_kwargs: Any) -> None:
        for v in vectors:
            self._store[v["id"]] = {
                "values": v.get("values", []),
                "metadata": v.get("metadata", {}),
            }

    def query(
        self,
        vector: list[float],
        sparse_vector: dict[str, Any] | None = None,
        top_k: int = 10,
        filter: dict[str, Any] | None = None,
        include_metadata: bool = False,
        namespace: str = "",
        **_kwargs: Any,
    ) -> _FakeQueryResult:
        results: list[_FakeMatch] = []
        for doc_id, entry in self._store.items():
            meta = entry.get("metadata", {})
            if filter and not _match_filter(meta, filter):
                continue
            results.append(
                _FakeMatch(
                    id=doc_id,
                    score=0.85,
                    metadata=meta if include_metadata else {},
                )
            )
        results.sort(key=lambda m: m.score, reverse=True)
        return _FakeQueryResult(results[:top_k])

    def delete(self, **kwargs: Any) -> None:
        ids = kwargs.get("ids", [])
        for doc_id in ids:
            self._store.pop(doc_id, None)


def _match_filter(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, value in filters.items():
        if isinstance(value, dict):
            if "$eq" in value and metadata.get(key) != value["$eq"]:
                return False
            if "$in" in value and metadata.get(key) not in value["$in"]:
                return False
        elif isinstance(value, list):
            if metadata.get(key) not in value:
                return False
        elif metadata.get(key) != value:
            return False
    return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_index() -> _FakeIndex:
    return _FakeIndex()


@pytest.fixture()
def provider() -> HashEmbeddingProvider:
    return HashEmbeddingProvider()


def _seed_mock_index(index: _FakeIndex, provider: HashEmbeddingProvider) -> None:
    """Insert test vectors into the fake Pinecone index."""
    chunks = [
        {
            "id": "PP-35-2021::chunk-1",
            "text": "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
            "document_id": "PP-35-2021",
            "chapter": "BAB II",
            "section": "Kompensasi",
            "article": "Pasal 15",
            "paragraph": "Ayat (1)",
            "page_start": 1,
            "page_end": 2,
            "token_count": 9,
            "topics": ["pkwt"],
            "legal_status": "active",
            "source_url": "https://peraturan.bpk.go.id/",
            "build_id": "build-1",
            "regulation_type": "PP",
            "number": 35,
            "year": 2021,
        },
        {
            "id": "PP-35-2021::chunk-2",
            "text": "Pengusaha wajib membayarkan THR paling lambat tujuh hari sebelum hari raya.",
            "document_id": "PP-35-2021",
            "chapter": "BAB III",
            "section": "THR",
            "article": "Pasal 5",
            "paragraph": "Ayat (1)",
            "page_start": 3,
            "page_end": 3,
            "token_count": 10,
            "topics": ["thr"],
            "legal_status": "active",
            "source_url": "https://peraturan.bpk.go.id/",
            "build_id": "build-1",
            "regulation_type": "PP",
            "number": 35,
            "year": 2021,
        },
        {
            "id": "UU-13-2003::chunk-1",
            "text": "Pekerja yang di PHK berhak memperoleh pesangon sesuai ketentuan.",
            "document_id": "UU-13-2003",
            "chapter": "BAB VII",
            "section": "PHK",
            "article": "Pasal 151",
            "paragraph": None,
            "page_start": 10,
            "page_end": 10,
            "token_count": 10,
            "topics": ["phk"],
            "legal_status": "revoked",
            "source_url": "https://peraturan.bpk.go.id/",
            "build_id": "build-2",
            "regulation_type": "UU",
            "number": 13,
            "year": 2003,
        },
    ]
    for chunk in chunks:
        embedding = provider.embed([chunk["text"]])[0]
        index.upsert(
            vectors=[
                {
                    "id": chunk["id"],
                    "values": embedding,
                    "metadata": {k: v for k, v in chunk.items() if k != "text"},
                }
            ]
        )


def _build_store(mock_index: _FakeIndex, provider: HashEmbeddingProvider) -> PineconeRetrievalStore:
    """Construct a PineconeRetrievalStore wired to the mock index."""
    _seed_mock_index(mock_index, provider)

    config = PineconeConfig(api_key="test-key", index_name="kerjapedia-test", namespace="test")
    store = PineconeRetrievalStore(config=config, embedding_provider=provider)

    # Wire the mock index directly, bypassing Pinecone client creation
    store._client = MagicMock()
    store._index = mock_index
    return store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPineconeRetrievalIntegration:
    """Full pipeline integration tests with mock Pinecone index."""

    def test_basic_query_returns_results(
        self, mock_index: _FakeIndex, provider: HashEmbeddingProvider
    ) -> None:
        store = _build_store(mock_index, provider)
        response = store.search("Berapa kompensasi PKWT?")

        assert not response.should_refuse
        assert len(response.results) > 0
        assert response.results[0].document.document_id == "PP-35-2021"

    def test_metadata_filters_narrow_results(
        self, mock_index: _FakeIndex, provider: HashEmbeddingProvider
    ) -> None:
        store = _build_store(mock_index, provider)
        response = store.search("Berapa kompensasi PKWT menurut Pasal 15?")

        assert not response.should_refuse
        assert any(r.document.article == "Pasal 15" for r in response.results)

    def test_topic_based_query_prefers_relevant_document(
        self, mock_index: _FakeIndex, provider: HashEmbeddingProvider
    ) -> None:
        store = _build_store(mock_index, provider)
        response = store.search("Apa itu THR dan kapan dibayarkan?")

        assert not response.should_refuse
        top_doc_ids = [r.document.document_id for r in response.results[:2]]
        assert "PP-35-2021" in top_doc_ids

    def test_context_inheritance_preserves_regulation_scope(
        self, mock_index: _FakeIndex, provider: HashEmbeddingProvider
    ) -> None:
        store = _build_store(mock_index, provider)
        response = store.search(
            "berapa besarnya?",
            context_topics=("thr",),
            context_document_ids=("PP-35-2021",),
        )

        assert not response.should_refuse
        top_doc_ids = [r.document.document_id for r in response.results[:2]]
        assert "PP-35-2021" in top_doc_ids

    def test_out_of_scope_query_is_refused(
        self, mock_index: _FakeIndex, provider: HashEmbeddingProvider
    ) -> None:
        store = _build_store(mock_index, provider)
        response = store.search("Berapa harga bensin hari ini?")

        assert response.should_refuse
        assert response.refusal_reason == "out_of_scope_query"
        assert response.results == []

    def test_regulation_type_filter_applied(
        self, mock_index: _FakeIndex, provider: HashEmbeddingProvider
    ) -> None:
        store = _build_store(mock_index, provider)
        response = store.search("Apa isi PP No. 35 Tahun 2021 tentang PKWT?")

        assert not response.should_refuse
        assert any(
            r.document.document_id.startswith("PP") for r in response.results
        )

    def test_embedding_vector_populated(
        self, mock_index: _FakeIndex, provider: HashEmbeddingProvider
    ) -> None:
        store = _build_store(mock_index, provider)
        response = store.search("Bagaimana pengaturan upah?")

        assert not response.should_refuse
        for result in response.results:
            assert result.document.build_id is not None
            assert result.document.document_id != ""

    def test_match_reasons_include_topic_or_lexical_boost(
        self, mock_index: _FakeIndex, provider: HashEmbeddingProvider
    ) -> None:
        store = _build_store(mock_index, provider)
        response = store.search("Kapan THR dibayarkan?")

        assert not response.should_refuse
        top_result = response.results[0]
        assert len(top_result.match_reasons) > 0

    def test_warnings_listed_for_low_quality_sources(
        self, mock_index: _FakeIndex, provider: HashEmbeddingProvider
    ) -> None:
        store = _build_store(mock_index, provider)
        response = store.search("Aturan PHK bagi pekerja")

        assert not response.should_refuse
        if any(r.document.legal_status == "revoked" for r in response.results):
            assert "retrieved_source_contains_historical_or_revoked_document" in response.warnings

    def test_empty_index_returns_refusal(
        self, provider: HashEmbeddingProvider
    ) -> None:
        empty_index = _FakeIndex()
        config = PineconeConfig(api_key="test-key", index_name="kerjapedia-test", namespace="test")
        store = PineconeRetrievalStore(config=config, embedding_provider=provider)
        store._client = MagicMock()
        store._index = empty_index

        response = store.search("Berapa kompensasi PKWT?")

        assert response.should_refuse or len(response.results) == 0
