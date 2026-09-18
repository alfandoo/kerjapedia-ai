"""Filter extraction contract: explicit asks produce filter dimensions.

The Pinecone-specific wiring tests (server filter mapping, legacy-namespace
fallback warnings, capability-probe caching) were retired with the Pinecone
pipeline. Filter semantics themselves live in
app.services.rag.indexing.filters (covered by test_rag_indexing) and query
understanding below.
"""

from app.services.retrieval.query import extract_filters


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
