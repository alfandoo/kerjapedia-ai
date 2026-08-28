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
from app.services.answering.groq_generator import GroqAnswerGenerator, _clean_answer_text
from app.services.ingestion.embeddings import BGEM3EmbeddingProvider
from app.services.ingestion.schemas import Chunk, DocumentMetadata, EmbeddedChunk
from app.services.retrieval.pinecone_store import PineconeConfig, PineconeRetrievalStore
from app.services.retrieval.schemas import RetrievalResponse


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


def test_bge_m3_provider_uses_lazy_sentence_transformer(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSentenceTransformer:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def encode(self, texts, normalize_embeddings: bool, show_progress_bar: bool):
            assert normalize_embeddings is True
            assert show_progress_bar is False
            return [[1.0] + [0.0] * 1023 for _ in texts]

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    provider = BGEM3EmbeddingProvider()
    vectors = provider.embed(["aturan pkwt"])

    assert len(vectors[0]) == 1024
    assert sum(value * value for value in vectors[0]) == pytest.approx(1.0)


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
            "filter": {
                "document_id": {"$eq": "PP-35-2021"},
                "version": {"$eq": 1},
            },
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
            assert kwargs["filter"] == {"topics": {"$in": ["pkwt"]}}
            assert kwargs["top_k"] == 100
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
    assert response.results[0].semantic_score == 0.91


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


class FakeGroqClient:
    def __init__(self, payload: dict | str) -> None:
        self.payload = payload
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        content = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
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


def test_groq_generator_accepts_structured_json() -> None:
    generator = GroqAnswerGenerator(api_key="test-key")
    generator._client = FakeGroqClient(
        {
            "answer": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
            "confidence": 0.82,
            "cited_chunk_ids": ["chunk-1"],
        }
    )

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.refusal_reason is None
    assert answer.confidence == 0.82
    assert answer.citations[0].chunk_id == "chunk-1"
    assert "Pekerja PKWT" in answer.answer


def test_groq_generator_removes_internal_chunk_ids_from_answer() -> None:
    generator = GroqAnswerGenerator(api_key="test-key")
    generator._client = FakeGroqClient(
        {
            "answer": (
                "Pekerja PKWT memperoleh kompensasi [[chunk-1]]. "
                "Ketentuannya tercantum dalam Pasal 15 [chunk-1]."
            ),
            "confidence": 0.82,
            "cited_chunk_ids": ["chunk-1"],
        }
    )

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert "chunk-1" not in answer.answer
    assert "[[" not in answer.answer
    assert "Pasal 15." in answer.answer


def test_groq_generator_returns_only_model_selected_citations() -> None:
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
    generator = GroqAnswerGenerator(api_key="test-key")
    generator._client = FakeGroqClient(
        {
            "answer": "Pembayaran diatur dalam Pasal 16.",
            "confidence": 0.8,
            "cited_chunk_ids": ["chunk-2"],
        }
    )

    answer = generator.generate("Kapan kompensasi dibayar?", retrieval)

    assert [citation.chunk_id for citation in answer.citations] == ["chunk-2"]
    assert answer.related_documents


def test_groq_generator_falls_back_on_bad_json_or_bad_citations() -> None:
    generator = GroqAnswerGenerator(api_key="test-key")
    generator._client = FakeGroqClient(
        {
            "answer": "Jawaban dengan citation salah.",
            "confidence": 0.9,
            "cited_chunk_ids": ["not-retrieved"],
        }
    )

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert "groq_answer_fallback_used" in answer.warnings
    assert answer.citations[0].chunk_id == "chunk-1"


def test_chat_ask_can_use_configured_pinecone_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with state.lock:
        state.request_counts.clear()
    monkeypatch.setattr(settings, "vector_store", "pinecone")
    monkeypatch.setattr(settings, "llm_provider", "local")
    monkeypatch.setattr(
        "app.api.routes_chat.pinecone_store_from_settings",
        lambda _: SimpleNamespace(
            search=lambda question, top_k: retrieval_response(),
        ),
    )

    response = TestClient(app).post(
        "/chat/ask",
        json={"question": "Apakah pekerja PKWT memperoleh kompensasi?", "top_k": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]["citations"][0]["chunk_id"] == "chunk-1"
    assert asdict(retrieval_response())["results"][0]["document"]["chunk_id"] == "chunk-1"
