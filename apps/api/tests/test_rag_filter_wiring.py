"""Wiring tests: new filter dimensions from query to Pinecone, with fallback.

Covers the contract: explicit asks produce new-dimension clauses;
legacy namespaces (schema 1, without the fields) drop them with a
warning instead of returning zero results; modern namespaces keep them.
"""

from types import SimpleNamespace

from app.services.rag.indexing.filters import build_filter
from app.services.retrieval.pinecone_store import (
    PineconeConfig,
    PineconeRetrievalStore,
    _pinecone_filter,
)
from app.services.retrieval.query import extract_filters


class StaticEmbeddingProvider:
    model_name = "test-embedding"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 1023 for _ in texts]


def _modern_metadata(**overrides):
    metadata = {
        "chunk_id": "chunk-1",
        "document_id": "PP-35-2021",
        "text": "Penjelasan Pasal 15 uang kompensasi pekerja yang masih berlaku.",
        "article": "Pasal 15",
        "page_start": 12,
        "page_end": 12,
        "token_count": 12,
        "topics": ["pkwt"],
        "legal_status": "active",
        "source_url": "https://peraturan.bpk.go.id/",
        "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
        "short_title": "PP 35/2021",
        "segment_kind": "explanation",
        "freshness_state": "fresh",
        "effective_date": "2021-01-01",
        "topics_chunk": ["pkwt"],
    }
    metadata.update(overrides)
    return metadata


def _legacy_metadata(**overrides):
    metadata = _modern_metadata(**overrides)
    for field in ("segment_kind", "freshness_state", "effective_date", "topics_chunk"):
        metadata.pop(field, None)
    return metadata


class ScriptedIndex:
    """Serves a probe response once, then canned search matches."""

    def __init__(self, probe_metadata=None, search_matches=()):
        self.calls = []
        self._probe_metadata = probe_metadata
        self._search_matches = list(search_matches)

    def query(self, **kwargs):
        self.calls.append(kwargs)
        if "filter" not in kwargs:
            if self._probe_metadata is None:
                return SimpleNamespace(matches=[])
            return SimpleNamespace(
                matches=[SimpleNamespace(id="probe-1", score=1.0, metadata=self._probe_metadata)]
            )
        return SimpleNamespace(matches=list(self._search_matches))


def _match(chunk_id="chunk-1", metadata=None):
    return SimpleNamespace(
        id=chunk_id,
        score=0.9,
        metadata=metadata if metadata is not None else _modern_metadata(chunk_id=chunk_id),
    )


def _store(index):
    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
    )
    store._index = index
    return store


def test_extract_filters_segment_kind_only_on_explicit_penjelasan() -> None:
    assert extract_filters("bagaimana penjelasan pasal 15 pp 35 tahun 2021?", ["pkwt"])[
        "segment_kinds"
    ] == ["explanation"]
    ordinary = extract_filters("apakah pekerja pkwt memperoleh kompensasi?", ["pkwt"])
    assert "segment_kinds" not in ordinary


def test_extract_filters_freshness_only_on_currency_language() -> None:
    assert extract_filters("aturan thr yang masih berlaku?", ["thr"])["freshness_states"] == [
        "fresh"
    ]
    assert extract_filters("aturan thr yang terkini?", ["thr"])["freshness_states"] == ["fresh"]
    ordinary = extract_filters("kapan batas waktu pembayaran thr?", ["thr"])
    assert "freshness_states" not in ordinary


def test_pinecone_filter_maps_new_keys_like_build_filter() -> None:
    filters = {
        "article": "Pasal 15",
        "segment_kinds": ["explanation"],
        "freshness_states": ["fresh"],
        "effective_on": "2024-01-01",
        "topics": ["pkwt"],
    }
    result = _pinecone_filter(filters, allow_unpublished=True, include_historical=True)
    expected = build_filter(
        article="Pasal 15",
        segment_kinds=["explanation"],
        freshness_states=["fresh"],
        effective_on="2024-01-01",
        topics=["pkwt"],
    )
    for key, clause in expected.items():
        assert result[key] == clause


def test_legacy_namespace_drops_new_filters_with_warning() -> None:
    index = ScriptedIndex(
        probe_metadata=_legacy_metadata(),
        search_matches=[_match(metadata=_legacy_metadata())],
    )
    store = _store(index)

    response = store.search(
        "Bagaimana penjelasan Pasal 15 PP 35 Tahun 2021 tentang kompensasi pekerja?",
        top_k=5,
    )

    assert response.results, "fallback must not empty the answer"
    assert "filter_unsupported_by_index:segment_kind" in response.warnings
    search_calls = [call for call in index.calls if "filter" in call]
    assert search_calls, "expected Pinecone search calls"
    for call in search_calls:
        assert "segment_kind" not in (call["filter"] or {})


def test_modern_namespace_keeps_new_filters() -> None:
    index = ScriptedIndex(
        probe_metadata=_modern_metadata(),
        search_matches=[_match()],
    )
    store = _store(index)

    response = store.search(
        "Bagaimana penjelasan Pasal 15 PP 35 Tahun 2021 tentang kompensasi pekerja?",
        top_k=5,
    )

    assert "filter_unsupported_by_index:segment_kind" not in response.warnings
    search_calls = [call for call in index.calls if "filter" in call]
    assert search_calls
    assert search_calls[0]["filter"]["segment_kind"] == {"$in": ["explanation"]}


def test_empty_namespace_fails_open_with_warning() -> None:
    index = ScriptedIndex(
        probe_metadata=None,
        search_matches=[_match(metadata=_legacy_metadata())],
    )
    store = _store(index)

    response = store.search(
        "Aturan THR yang masih berlaku untuk pekerja?",
        top_k=5,
    )

    assert response.results
    assert "filter_unsupported_by_index:freshness_state" in response.warnings


def test_capability_probe_is_cached_per_namespace() -> None:
    index = ScriptedIndex(
        probe_metadata=_modern_metadata(),
        search_matches=[_match()],
    )
    store = _store(index)
    query = "Bagaimana penjelasan Pasal 15 PP 35 Tahun 2021 tentang kompensasi pekerja?"

    store.search(query, top_k=5)
    probe_calls = len([call for call in index.calls if "filter" not in call])
    store.search(query, top_k=5)
    assert len([call for call in index.calls if "filter" not in call]) == probe_calls
