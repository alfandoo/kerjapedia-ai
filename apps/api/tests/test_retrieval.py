from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.query import understand_query
from app.services.retrieval.schemas import RetrievalDocument


def make_document(
    chunk_id: str,
    text: str,
    topics: list[str],
    article: str | None = None,
    legal_status: str = "needs_verification",
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
        page_start=1,
        page_end=1,
        token_count=len(text.split()),
        topics=topics,
        legal_status=legal_status,
        source_url="https://peraturan.bpk.go.id/",
        embedding_model=provider.model_name,
        embedding=provider.embed([text])[0],
        metadata={"year": 2021, "regulation_type": "PP"},
    )


def test_query_understanding_expands_abbreviations() -> None:
    query = understand_query("Berapa lama batas maksimal PKWT?")

    assert "pkwt" in query.detected_topics
    assert "duration" in query.detected_intents
    assert any("perjanjian kerja waktu tertentu" in item for item in query.rewritten_queries)


def test_retrieval_prefers_relevant_legal_chunk() -> None:
    engine = RetrievalEngine(
        documents=[
            make_document(
                "chunk-1",
                "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
                ["pkwt"],
                article="Pasal 15",
            ),
            make_document(
                "chunk-2",
                "Serikat pekerja berhak membuat perjanjian kerja bersama.",
                ["serikat_pekerja"],
            ),
        ],
        top_k=2,
    )

    response = engine.search("Apakah pekerja PKWT memperoleh kompensasi?")

    assert not response.should_refuse
    assert response.results[0].document.chunk_id == "chunk-1"
    assert "topic_match" in response.results[0].match_reasons
    assert "retrieved_source_status_needs_verification" in response.warnings


def test_retrieval_refuses_when_no_context_passes_threshold() -> None:
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

    response = engine.search("Bagaimana aturan THR?")

    assert response.should_refuse
    assert response.refusal_reason == "no_retrieved_chunk_passed_minimum_score"
