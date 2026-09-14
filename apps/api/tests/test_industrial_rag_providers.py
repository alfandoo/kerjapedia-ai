from __future__ import annotations

import json
import sys
import types
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.state import state
from app.core.config import settings
from app.main import app
from app.services.answering.openrouter_generator import (
    OpenRouterAnswerGenerator,
    _clean_answer_text,
)
from app.services.answering.schemas import HistoryTurn
from app.services.ingestion.embeddings import BGEM3EmbeddingProvider
from app.services.ingestion.schemas import Chunk, DocumentMetadata, EmbeddedChunk
from app.services.retrieval.pinecone_store import (
    PineconeConfig,
    PineconeRetrievalStore,
    _pinecone_filter,
)
from app.services.retrieval.schemas import RankedChunk, RetrievalDocument, RetrievalResponse


class StaticEmbeddingProvider:
    model_name = "test-embedding"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 1023 for _ in texts]


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


def sample_embedded_chunk() -> EmbeddedChunk:
    chunk = Chunk(
        chunk_id="chunk-1",
        document_id="PP-35-2021",
        chapter="BAB II",
        section="PKWT",
        article="Pasal 15",
        paragraph="Ayat (1)",
        page_start=12,
        page_end=12,
        text="Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
        token_count=8,
        topics=["pkwt"],
        legal_status="active",
        source_url="https://peraturan.bpk.go.id/",
    )
    return EmbeddedChunk(chunk=chunk, embedding_model="BAAI/bge-m3", embedding=[1.0] + [0.0] * 1023)


def test_bge_m3_provider_uses_lazy_sentence_transformer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSentenceTransformer:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def encode(
            self,
            texts,
            normalize_embeddings: bool,
            show_progress_bar: bool,
            batch_size: int,
        ):
            assert normalize_embeddings is True
            assert show_progress_bar is False
            assert batch_size == 16
            return [[1.0] + [0.0] * 1023 for _ in texts]

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    provider = BGEM3EmbeddingProvider()
    vectors = provider.embed(["aturan pkwt"])

    assert len(vectors[0]) == 1024
    assert sum(value * value for value in vectors[0]) == pytest.approx(1.0)


def test_bge_m3_hybrid_uses_lexical_sparse_fallback_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "FlagEmbedding", None)
    provider = BGEM3EmbeddingProvider(require_native_sparse=False)
    monkeypatch.setattr(
        provider,
        "embed",
        lambda texts: [[1.0] + [0.0] * 1023 for _ in texts],
    )

    batch = provider.embed_hybrid(["kapan THR dibayar"])

    assert len(batch.dense[0]) == 1024
    assert batch.sparse[0]
    assert provider.sparse_fallback_used is True


def test_bge_m3_hybrid_fails_closed_without_native_sparse_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "FlagEmbedding", None)
    provider = BGEM3EmbeddingProvider(require_native_sparse=True)

    with pytest.raises(RuntimeError, match="FlagEmbedding is required"):
        provider.embed_hybrid(["kapan THR dibayar"])


def test_pinecone_upsert_builds_flat_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []
    deleted: list[dict] = []

    class FakeIndex:
        def delete(self, namespace: str, filter: dict):
            deleted.append({"namespace": namespace, "filter": filter})

        def upsert(self, vectors, namespace: str):
            captured.extend(vectors)
            assert namespace == "production"
            return SimpleNamespace(upserted_count=len(vectors))

    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
    )
    store._index = FakeIndex()
    monkeypatch.setattr(store, "ensure_index", lambda: None)

    upserted = store.upsert_document(sample_document(), 1, [sample_embedded_chunk()])

    assert upserted == 1
    assert deleted == [
        {
            "namespace": "production",
            "filter": {"document_id": {"$eq": "PP-35-2021"}},
        }
    ]
    assert captured[0]["id"] == "chunk-1"
    metadata = captured[0]["metadata"]
    assert metadata["document_id"] == "PP-35-2021"
    assert metadata["article"] == "Pasal 15"
    assert metadata["topics"] == ["pkwt"]
    assert all(not isinstance(value, dict) for value in metadata.values())


def test_pinecone_search_returns_ranked_retrieval_response() -> None:
    class FakeIndex:
        def query(self, **kwargs):
            assert kwargs["namespace"] == "production"
            assert kwargs["filter"] == {"legal_status": {"$in": ["active", "amended"]}}
            assert kwargs["top_k"] == 100
            assert kwargs["sparse_vector"]["indices"]
            return SimpleNamespace(
                matches=[
                    SimpleNamespace(
                        id="chunk-1",
                        score=0.91,
                        metadata={
                            "chunk_id": "chunk-1",
                            "document_id": "PP-35-2021",
                            "text": "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
                            "article": "Pasal 15",
                            "paragraph": "Ayat (1)",
                            "page_start": 12,
                            "page_end": 12,
                            "token_count": 8,
                            "topics": ["pkwt"],
                            "legal_status": "active",
                            "source_url": "https://peraturan.bpk.go.id/",
                            "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
                            "short_title": "PP 35/2021",
                            "regulation_type": "PP",
                            "year": 2021,
                        },
                    )
                ]
            )

    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
    )
    store._index = FakeIndex()

    response = store.search("Apakah pekerja PKWT memperoleh kompensasi?", top_k=1)

    assert isinstance(response, RetrievalResponse)
    assert not response.should_refuse
    assert response.results[0].document.chunk_id == "chunk-1"
    # Single-candidate semantic scores min-max normalize to 1.0 so the
    # reranker sees a query-independent scale.
    assert response.results[0].semantic_score == 1.0


def test_pinecone_search_fuses_candidates_across_rewritten_queries() -> None:
    calls: list[dict] = []

    def match(chunk_id: str, text: str, article: str):
        return SimpleNamespace(
            id=chunk_id,
            score=0.9,
            metadata={
                "chunk_id": chunk_id,
                "document_id": "PP-35-2021",
                "text": text,
                "article": article,
                "page_start": 12,
                "page_end": 12,
                "token_count": 8,
                "topics": ["pkwt"],
                "legal_status": "active",
                "source_url": "https://peraturan.bpk.go.id/",
                "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
                "short_title": "PP 35/2021",
            },
        )

    class FusingIndex:
        def query(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return SimpleNamespace(
                    matches=[match("chunk-focus", "Pasal 15 uang kompensasi PKWT.", "Pasal 15")]
                )
            return SimpleNamespace(
                matches=[match("chunk-generic", "Pasal 8 jangka waktu PKWT.", "Pasal 8")]
            )

    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
    )
    store._index = FusingIndex()

    # Three rewrites (original, abbreviation expansion, compensation expansion).
    response = store.search("Apakah pekerja PKWT memperoleh kompensasi?", top_k=5)

    assert len(calls) == 3
    assert {item.document.chunk_id for item in response.results} == {
        "chunk-focus",
        "chunk-generic",
    }


def test_legacy_pinecone_index_retries_dense_only_in_development() -> None:
    calls: list[dict] = []

    class LegacyIndex:
        def query(self, **kwargs):
            calls.append(kwargs)
            if "sparse_vector" in kwargs:
                raise RuntimeError(
                    "[400] Index configuration does not support sparse values - "
                    "only indexes that are sparse or using dotproduct are supported"
                )
            return SimpleNamespace(
                matches=[
                    SimpleNamespace(
                        id="chunk-1",
                        score=0.91,
                        metadata={
                            "chunk_id": "chunk-1",
                            "document_id": "PP-35-2021",
                            "text": "Pasal 15 pekerja PKWT berhak memperoleh kompensasi.",
                            "article": "Pasal 15",
                            "page_start": 12,
                            "page_end": 12,
                            "token_count": 8,
                            "topics": ["pkwt"],
                            "legal_status": "active",
                            "source_url": "https://peraturan.bpk.go.id/",
                            "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
                        },
                    )
                ]
            )

    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
        fail_closed=False,
    )
    store._index = LegacyIndex()

    response = store.search("Apakah pekerja PKWT memperoleh kompensasi?", top_k=1)

    # Three rewritten queries: one sparse attempt fails over to dense-only,
    # then each rewrite is retried without sparse values.
    assert len(calls) == 4
    assert "sparse_vector" in calls[0]
    assert all("sparse_vector" not in call for call in calls[1:])
    assert "pinecone_index_requires_dotproduct" in response.warnings
    assert response.results[0].document.chunk_id == "chunk-1"


def test_legacy_pinecone_index_stays_fail_closed_in_production() -> None:
    class LegacyIndex:
        def query(self, **kwargs):
            raise RuntimeError(
                "[400] Index configuration does not support sparse values - "
                "only indexes that are sparse or using dotproduct are supported"
            )

    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
        fail_closed=True,
    )
    store._index = LegacyIndex()

    with pytest.raises(RuntimeError, match="does not support sparse values"):
        store.search("Apakah pekerja PKWT memperoleh kompensasi?", top_k=1)


@pytest.mark.parametrize(
    ("fail_closed", "expected"),
    [(False, True), (True, False)],
)
def test_legacy_pinecone_readiness_is_development_only(
    fail_closed: bool,
    expected: bool,
) -> None:
    class FakeIndexes:
        def describe(self, _name: str):
            return SimpleNamespace(
                dimension=1024,
                metric="cosine",
                status=SimpleNamespace(ready=True),
            )

    class FakeClient:
        indexes = FakeIndexes()

    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
        fail_closed=fail_closed,
    )
    store._client = FakeClient()

    assert store.is_ready() is expected


def test_pinecone_refuses_out_of_scope_query_before_embedding() -> None:
    class FailingEmbeddingProvider:
        model_name = "unused"

        def embed(self, texts):
            raise AssertionError("out-of-scope query must not be embedded")

    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        FailingEmbeddingProvider(),
    )

    response = store.search("Berapa tarif pajak kendaraan?", top_k=1)

    assert response.should_refuse
    assert response.refusal_reason == "out_of_scope_query"
    assert response.results == []


def test_production_pinecone_filter_excludes_unpublished_and_stale_sources() -> None:
    assert _pinecone_filter(
        {},
        allow_unpublished=False,
        include_historical=False,
    ) == {
        "legal_status": {"$in": ["active", "amended"]},
        "publication_status": {"$eq": "published"},
        "source_verification_status": {"$eq": "verified"},
        "legal_review_status": {"$eq": "verified"},
        "is_current": {"$eq": True},
    }


def test_explicit_historical_filter_keeps_verification_gate_without_current_gate() -> None:
    result = _pinecone_filter(
        {},
        allow_unpublished=False,
        include_historical=True,
    )

    assert result["publication_status"] == {"$eq": "published"}
    assert result["legal_review_status"] == {"$eq": "verified"}
    assert "is_current" not in result
    assert "legal_status" not in result


def test_pinecone_filter_applies_explicit_regulation_number_as_hard_filter() -> None:
    result = _pinecone_filter(
        {"regulation_type": "Permenaker", "number": 6, "year": 2016},
        allow_unpublished=False,
        include_historical=False,
    )

    assert result["regulation_type"] == {"$eq": "Permenaker"}
    assert result["number"] == {"$eq": 6}
    assert result["year"] == {"$eq": 2016}


class FakeOpenRouterClient:
    def __init__(self, payload: dict | str | Exception | list[dict | str | Exception]) -> None:
        self.payloads = payload if isinstance(payload, list) else [payload]
        self.calls = 0
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.requests.append(kwargs)
        payload = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        if isinstance(payload, Exception):
            raise payload
        content = payload if isinstance(payload, str) else json.dumps(payload)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def retrieval_response() -> RetrievalResponse:
    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
    )
    store._index = SimpleNamespace(
        query=lambda **_: SimpleNamespace(
            matches=[
                SimpleNamespace(
                    id="chunk-1",
                    score=0.91,
                    metadata={
                        "chunk_id": "chunk-1",
                        "document_id": "PP-35-2021",
                        "text": "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
                        "article": "Pasal 15",
                        "page_start": 12,
                        "page_end": 12,
                        "token_count": 8,
                        "topics": ["pkwt"],
                        "legal_status": "active",
                        "source_url": "https://peraturan.bpk.go.id/",
                        "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
                        "short_title": "PP 35/2021",
                    },
                )
            ]
        )
    )
    return store.search("Apakah pekerja PKWT memperoleh kompensasi?", top_k=1)


def test_clean_answer_text_preserves_paragraphs_and_compact_lists() -> None:
    answer = (
        "Jawaban langsung pada baris pertama.\n"
        "Baris lanjutan tetap menjadi paragraf yang sama.\n\n"
        "- Syarat pertama\n"
        "- Syarat kedua\n\n"
        "Catatan praktis penutup."
    )

    cleaned = _clean_answer_text(answer, [])

    assert cleaned == (
        "Jawaban langsung pada baris pertama. Baris lanjutan tetap menjadi paragraf yang sama.\n\n"
        "- Syarat pertama\n- Syarat kedua\n\n"
        "Catatan praktis penutup."
    )


def test_clean_answer_text_removes_chunk_ids_without_breaking_prose() -> None:
    cleaned = _clean_answer_text(
        "Hak pekerja diatur dalam Pasal 15 [[chunk-1]].\nLihat ketentuan terkait [chunk-1].",
        ["chunk-1"],
    )

    assert "chunk-1" not in cleaned
    assert cleaned == "Hak pekerja diatur dalam Pasal 15. Lihat ketentuan terkait."


def test_openrouter_generator_accepts_structured_json() -> None:
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = FakeOpenRouterClient(
        {
            "answer": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
            "cited_chunk_ids": ["chunk-1"],
            "claims": [
                {
                    "text": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
                    "cited_chunk_ids": ["chunk-1"],
                }
            ],
        }
    )

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.refusal_reason is None
    assert answer.confidence != 0.82
    assert 0 < answer.confidence <= 0.95
    assert answer.claims
    assert all(claim.supported for claim in answer.claims)
    assert answer.citations[0].chunk_id == "chunk-1"
    assert "Pekerja PKWT" in answer.answer


def test_openrouter_generator_removes_internal_chunk_ids_from_answer() -> None:
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = FakeOpenRouterClient(
        {
            "answer": (
                "Pekerja PKWT memperoleh kompensasi [[chunk-1]]. "
                "Ketentuannya tercantum dalam Pasal 15 [chunk-1]."
            ),
            "cited_chunk_ids": ["chunk-1"],
            "claims": [
                {
                    "text": (
                        "Pekerja PKWT memperoleh kompensasi. Ketentuannya tercantum dalam Pasal 15."
                    ),
                    "cited_chunk_ids": ["chunk-1"],
                }
            ],
        }
    )

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert "chunk-1" not in answer.answer
    assert "[[" not in answer.answer
    assert "Pasal 15." in answer.answer


def test_openrouter_generator_returns_only_model_selected_citations() -> None:
    retrieval = retrieval_response()
    first = retrieval.results[0]
    second = replace(
        first,
        document=replace(
            first.document,
            chunk_id="chunk-2",
            text="Pasal 16 mengatur waktu pembayaran kompensasi.",
        ),
    )
    retrieval = replace(retrieval, results=[first, second])
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = FakeOpenRouterClient(
        {
            "answer": "Pembayaran diatur dalam Pasal 16.",
            "cited_chunk_ids": ["chunk-2"],
            "claims": [
                {
                    "text": "Pembayaran diatur dalam Pasal 16.",
                    "cited_chunk_ids": ["chunk-2"],
                }
            ],
        }
    )

    answer = generator.generate("Kapan kompensasi dibayar?", retrieval)

    assert [citation.chunk_id for citation in answer.citations] == ["chunk-2"]
    assert answer.related_documents


def test_openrouter_generator_derives_top_level_citations_from_valid_claims() -> None:
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = FakeOpenRouterClient(
        {
            "answer": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
            "claims": [
                {
                    "text": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
                    "cited_chunk_ids": ["chunk-1"],
                }
            ],
        }
    )

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert answer.citations[0].chunk_id == "chunk-1"


def test_openrouter_generator_repairs_one_invalid_response() -> None:
    client = FakeOpenRouterClient(
        [
            {
                "answer": "Jawaban dengan citation salah.",
                "cited_chunk_ids": ["not-retrieved"],
                "claims": [
                    {
                        "text": "Jawaban dengan citation salah.",
                        "cited_chunk_ids": ["not-retrieved"],
                    }
                ],
            },
            {
                "answer": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
                "cited_chunk_ids": ["chunk-1"],
                "claims": [
                    {
                        "text": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
                        "cited_chunk_ids": ["chunk-1"],
                    }
                ],
            },
        ]
    )
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert answer.debug["generation_attempts"] == 2
    assert client.calls == 2
    assert (
        "previous response failed validation"
        in client.requests[1]["messages"][1]["content"].lower()
    )


def test_openrouter_generator_retries_structured_output_bad_request_once() -> None:
    bad_request_error = type("BadRequestError", (Exception,), {})
    client = FakeOpenRouterClient(
        [
            bad_request_error("structured output rejected"),
            {
                "answer": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
                "cited_chunk_ids": ["chunk-1"],
                "claims": [
                    {
                        "text": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
                        "cited_chunk_ids": ["chunk-1"],
                    }
                ],
            },
        ]
    )
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert answer.debug["generation_attempts"] == 2
    assert client.calls == 2


def test_openrouter_generator_keeps_verified_primary_claim_when_repair_fails() -> None:
    bad_request_error = type("BadRequestError", (Exception,), {})
    main_claim = "Pekerja PKWT berhak memperoleh uang kompensasi berdasarkan Pasal 15."
    client = FakeOpenRouterClient(
        [
            {
                "answer": (f"{main_claim} Denda kompensasi dibayarkan kepada pemerintah daerah."),
                "cited_chunk_ids": ["chunk-1"],
                "claims": [
                    {
                        "text": main_claim,
                        "cited_chunk_ids": ["chunk-1"],
                    },
                    {
                        "text": "Denda kompensasi dibayarkan kepada pemerintah daerah.",
                        "cited_chunk_ids": ["chunk-1"],
                    },
                ],
            },
            bad_request_error("repair request rejected"),
        ]
    )
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert answer.answer == main_claim
    assert "pemerintah daerah" not in answer.answer
    assert answer.claims[0].supported is True
    assert [citation.chunk_id for citation in answer.citations] == ["chunk-1"]
    assert "answer_repaired_by_claim_pruning" in answer.warnings
    assert client.calls == 2


def test_openrouter_generator_fails_closed_without_exposing_raw_chunks() -> None:
    client = FakeOpenRouterClient(["not-json", "still-not-json"])
    generator = OpenRouterAnswerGenerator(api_key="test-key", fail_closed=True)
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "temporarily_unavailable"
    assert answer.confidence == 0
    assert answer.claims == []
    assert "answer_generation_unavailable" in answer.warnings
    assert answer.citations[0].chunk_id == "chunk-1"
    assert "Pasal 15 pekerja" not in answer.answer
    assert client.calls == 2


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Apakah pekerja PKWT memperoleh kompensasi?", "jawaban terverifikasi"),
        ("Are fixed-term workers entitled to compensation?", "verified answer"),
    ],
)
def test_openrouter_provider_failure_is_localized(query: str, expected: str) -> None:
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = FakeOpenRouterClient(RuntimeError("provider unavailable"))

    answer = generator.generate(query, retrieval_response())

    assert answer.answer_status == "temporarily_unavailable"
    assert expected in answer.answer.lower()
    assert answer.debug["failure_category"] == "provider_failure"


@pytest.mark.usefixtures("verify_test_schema")
def test_chat_ask_can_use_configured_pinecone_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with state.lock:
        state.request_counts.clear()
    monkeypatch.setattr(settings, "vector_store", "pinecone")
    monkeypatch.setattr(settings, "llm_provider", "local")
    monkeypatch.setattr(
        "app.api.routes_chat.pinecone_store_from_settings",
        lambda *_, **__: SimpleNamespace(
            search=lambda question, top_k, min_final_score, **kwargs: retrieval_response(),
        ),
    )

    response = TestClient(app).post(
        "/chat/ask",
        headers={"X-KerjaPedia-Guest-ID": "00000000-0000-4000-8000-000000000002"},
        json={"question": "Apakah pekerja PKWT memperoleh kompensasi?", "top_k": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]["citations"][0]["chunk_id"] == "chunk-1"
    assert asdict(retrieval_response())["results"][0]["document"]["chunk_id"] == "chunk-1"


def _ranked_pkwt_chunk() -> RankedChunk:
    document = RetrievalDocument(
        chunk_id="chunk-1",
        document_id="PP-35-2021",
        text="Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
        chapter="BAB II",
        section="PKWT",
        article="Pasal 15",
        paragraph="Ayat (1)",
        page_start=12,
        page_end=12,
        token_count=8,
        topics=["pkwt"],
        legal_status="active",
        source_url="https://peraturan.bpk.go.id/",
        embedding_model="test-embedding",
        embedding=[1.0] + [0.0] * 1023,
        metadata={"title": "PP 35/2021", "short_title": "PP 35/2021"},
    )
    return RankedChunk(
        document=document,
        lexical_score=0.5,
        semantic_score=0.6,
        fusion_score=0.02,
        rerank_score=0.4,
        final_score=0.4,
        match_reasons=[],
    )


def test_pinecone_model_rerank_failure_falls_back_open(monkeypatch: pytest.MonkeyPatch) -> None:
    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
        reranker_provider="pinecone",
    )
    monkeypatch.setattr(
        store,
        "_pinecone_client",
        lambda: (_ for _ in ()).throw(RuntimeError("reranker down")),
    )
    ranked = [_ranked_pkwt_chunk()]

    result, cross_encoder_ok = store._model_rerank("kompensasi PKWT", ranked)

    assert cross_encoder_ok is False
    assert result == ranked


def test_pinecone_model_rerank_failure_fail_closed_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
        reranker_provider="pinecone",
        fail_closed=True,
    )
    monkeypatch.setattr(
        store,
        "_pinecone_client",
        lambda: (_ for _ in ()).throw(RuntimeError("reranker down")),
    )

    with pytest.raises(RuntimeError, match="reranker is unavailable"):
        store._model_rerank("kompensasi PKWT", [_ranked_pkwt_chunk()])


def test_pinecone_search_warns_when_cross_encoder_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeIndex:
        def query(self, **kwargs):
            return SimpleNamespace(
                matches=[
                    SimpleNamespace(
                        id="chunk-1",
                        score=0.91,
                        metadata={
                            "chunk_id": "chunk-1",
                            "document_id": "PP-35-2021",
                            "text": "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
                            "article": "Pasal 15",
                            "paragraph": "Ayat (1)",
                            "page_start": 12,
                            "page_end": 12,
                            "token_count": 8,
                            "topics": ["pkwt"],
                            "legal_status": "active",
                            "source_url": "https://peraturan.bpk.go.id/",
                            "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
                            "short_title": "PP 35/2021",
                            "regulation_type": "PP",
                            "year": 2021,
                        },
                    )
                ]
            )

    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
        reranker_provider="pinecone",
    )
    store._index = FakeIndex()
    monkeypatch.setattr(
        store,
        "_pinecone_client",
        lambda: (_ for _ in ()).throw(RuntimeError("reranker down")),
    )

    response = store.search("Apakah pekerja PKWT memperoleh kompensasi?", top_k=1)

    assert not response.should_refuse
    assert "cross_encoder_rerank_unavailable" in response.warnings
    assert response.results[0].document.chunk_id == "chunk-1"


def _three_chunk_retrieval() -> RetrievalResponse:
    texts = [
        ("chunk-1", "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.", "Pasal 15"),
        (
            "chunk-2",
            "Ketentuan perhitungan kompensasi diatur lebih lanjut oleh menteri.",
            "Pasal 16",
        ),
        (
            "chunk-3",
            "Waktu kerja lembur diatur dalam peraturan perusahaan tersendiri.",
            "Pasal 77",
        ),
    ]
    store = PineconeRetrievalStore(
        PineconeConfig(api_key="test-key"),
        StaticEmbeddingProvider(),
    )
    store._index = SimpleNamespace(
        query=lambda **_: SimpleNamespace(
            matches=[
                SimpleNamespace(
                    id=chunk_id,
                    score=0.90 - index * 0.01,
                    metadata={
                        "chunk_id": chunk_id,
                        "document_id": "PP-35-2021",
                        "text": text,
                        "article": article,
                        "page_start": 12,
                        "page_end": 12,
                        "token_count": 8,
                        "topics": ["pkwt"],
                        "legal_status": "active",
                        "source_url": "https://peraturan.bpk.go.id/",
                        "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
                        "short_title": "PP 35/2021",
                    },
                )
                for index, (chunk_id, text, article) in enumerate(texts)
            ]
        )
    )
    return store.search("Apakah pekerja PKWT memperoleh kompensasi?", top_k=3)


def test_openrouter_prompt_contains_only_citable_chunks_and_history() -> None:
    generator = OpenRouterAnswerGenerator(api_key="test-key", max_citations=2)
    generator._client = FakeOpenRouterClient(
        {
            "answer": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
            "cited_chunk_ids": ["chunk-1"],
            "claims": [
                {
                    "text": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
                    "cited_chunk_ids": ["chunk-1"],
                }
            ],
        }
    )
    retrieval = _three_chunk_retrieval()
    assert len(retrieval.results) == 3

    answer = generator.generate(
        "Kalau kontraknya dua tahun, berapa kompensasi yang wajib dibayar?",
        retrieval,
        history=(
            HistoryTurn(
                question="Apakah pekerja PKWT mendapat kompensasi?",
                answer="Ya, pekerja PKWT berhak memperoleh kompensasi.",
            ),
        ),
    )

    assert answer.refusal_reason is None
    user_content = generator._client.requests[0]["messages"][1]["content"]
    assert "[1]" in user_content and "[2]" in user_content
    assert "[3]" not in user_content
    assert "Waktu kerja lembur" not in user_content
    assert "Riwayat percakapan" in user_content
    assert "Apakah pekerja PKWT mendapat kompensasi?" in user_content
    assert answer.debug["history_turns"] == 1
