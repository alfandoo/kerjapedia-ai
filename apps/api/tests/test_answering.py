from app.services.answering.generator import AnswerGenerator
from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.schemas import RetrievalDocument


def make_document(
    chunk_id: str,
    text: str,
    topics: list[str],
    article: str | None = None,
    legal_status: str = "active",
) -> RetrievalDocument:
    provider = HashEmbeddingProvider()
    return RetrievalDocument(
        chunk_id=chunk_id,
        document_id="PP-35-2021",
        text=text,
        chapter="BAB II",
        section="Perjanjian Kerja Waktu Tertentu",
        article=article,
        paragraph="Ayat (1)",
        page_start=12,
        page_end=12,
        token_count=len(text.split()),
        topics=topics,
        legal_status=legal_status,
        source_url="https://peraturan.bpk.go.id/",
        embedding_model=provider.model_name,
        embedding=provider.embed([text])[0],
        metadata={
            "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
            "short_title": "PP 35/2021",
            "local_file": "dataset/PP-35-2021.pdf",
            "year": 2021,
            "regulation_type": "PP",
        },
    )


def test_answer_generation_returns_structured_citations() -> None:
    engine = RetrievalEngine(
        documents=[
            make_document(
                "chunk-1",
                "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
                ["pkwt"],
                article="Pasal 15",
            )
        ]
    )
    retrieval = engine.search("Apakah pekerja PKWT memperoleh kompensasi?")

    response = AnswerGenerator().generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval,
    )

    assert response.refusal_reason is None
    assert response.clarification_question is None
    assert response.citations[0].document_id == "PP-35-2021"
    assert response.citations[0].article == "Pasal 15"
    assert response.confidence > 0
    assert response.related_documents[0].short_title == "PP 35/2021"
    assert response.prompt_version_id == "kerjapedia-grounded-answer-v2"
    assert "bukan pengganti advokat" in response.disclaimer


def test_answer_generation_refuses_when_retrieval_is_weak() -> None:
    engine = RetrievalEngine(
        documents=[
            make_document(
                "chunk-1",
                "Serikat pekerja berhak membuat perjanjian kerja bersama.",
                ["serikat_pekerja"],
            )
        ],
        min_final_score=10.0,
    )
    retrieval = engine.search("Bagaimana aturan THR?")

    response = AnswerGenerator().generate("Bagaimana aturan THR?", retrieval)

    assert response.refusal_reason == "no_retrieved_chunk_passed_minimum_score"
    assert response.citations == []
    assert response.confidence == 0.0


def test_answer_generation_explains_out_of_scope_boundary() -> None:
    engine = RetrievalEngine(
        documents=[
            make_document(
                "chunk-1",
                "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
                ["pkwt"],
            )
        ]
    )
    retrieval = engine.search("Siapa presiden Prancis?")

    response = AnswerGenerator().generate("Siapa presiden Prancis?", retrieval)

    assert response.refusal_reason == "out_of_scope_query"
    assert response.citations == []
    assert "saya tidak tahu" in response.answer.lower()
    assert "ketenagakerjaan Indonesia" in response.answer


def test_answer_generation_asks_clarification_for_ambiguous_question() -> None:
    engine = RetrievalEngine(
        documents=[
            make_document(
                "chunk-1",
                "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
                ["pkwt"],
            )
        ]
    )
    retrieval = engine.search("Hak saya apa?")

    response = AnswerGenerator().generate("Hak saya apa?", retrieval)

    assert response.clarification_question is not None
    assert response.refusal_reason is None
    assert response.citations == []
