from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.query import understand_query
from app.services.retrieval.relationships import (
    RegulationRelationship,
    build_relationship_index,
    relationship_index_for_manifest,
)
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


def test_query_understanding_expands_legal_timing_terms() -> None:
    query = understand_query("Kapan batas waktu pembayaran THR?")

    assert any("paling lambat" in item for item in query.rewritten_queries)
    assert any("wajib dibayarkan" in item for item in query.rewritten_queries)


def test_retrieval_refuses_query_outside_employment_scope() -> None:
    engine = RetrievalEngine(documents=[])

    response = engine.search("Berapa tarif pajak kendaraan?")

    assert response.should_refuse
    assert response.refusal_reason == "out_of_scope_query"
    assert response.results == []


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


def make_relationship_document(
    chunk_id: str,
    document_id: str,
    text: str,
    topics: list[str],
    legal_status: str = "needs_verification",
) -> RetrievalDocument:
    provider = HashEmbeddingProvider()
    return RetrievalDocument(
        chunk_id=chunk_id,
        document_id=document_id,
        text=text,
        chapter="BAB II",
        section="Ketentuan",
        article="Pasal 1",
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


def test_relationship_index_builds_superseding_lookup() -> None:
    index = build_relationship_index(
        [
            RegulationRelationship(
                from_document_id="PP-36-2021",
                to_document_id="PP-51-2023",
                relationship_type="amended_by",
            ),
            RegulationRelationship(
                from_document_id="PP-36-2021",
                to_document_id="UU-13-2003",
                relationship_type="related_to",
            ),
        ]
    )

    assert index.superseded_by["PP-36-2021"] == ["PP-51-2023"]
    assert "PP-51-2023" not in index.superseded_by


def test_revoked_document_superseded_by_active_document_is_penalized() -> None:
    old_doc = make_relationship_document(
        "old-chunk",
        "PP-36-2021",
        "Pengupahan diatur dalam peraturan pemerintah ini.",
        ["pengupahan"],
        legal_status="revoked",
    )
    new_doc = make_relationship_document(
        "new-chunk",
        "PP-51-2023",
        "Pengupahan diatur dalam peraturan pemerintah ini.",
        ["pengupahan"],
        legal_status="active",
    )
    index = build_relationship_index(
        [
            RegulationRelationship(
                from_document_id="PP-36-2021",
                to_document_id="PP-51-2023",
                relationship_type="amended_by",
            )
        ]
    )
    engine = RetrievalEngine(
        documents=[new_doc, old_doc],
        top_k=2,
        relationship_index=index,
    )
    without_index = RetrievalEngine(documents=[new_doc, old_doc], top_k=2)

    response = engine.search("Bagaimana pengaturan upah?")
    baseline = without_index.search("Bagaimana pengaturan upah?")

    old_ranked = next(
        item for item in response.results if item.document.chunk_id == "old-chunk"
    )
    old_baseline = next(
        item for item in baseline.results if item.document.chunk_id == "old-chunk"
    )
    assert "superseded_by_newer_document" in old_ranked.match_reasons
    assert old_ranked.final_score < old_baseline.final_score
    assert "retrieved_source_superseded_by_newer_document" in response.warnings
    assert "retrieved_source_revoked_or_superseded_document" in response.warnings


def test_relationship_index_loaded_from_manifest_file() -> None:
    import json
    import tempfile
    from pathlib import Path

    manifest = Path(tempfile.mkdtemp()) / "metadata.json"
    manifest.write_text(
        json.dumps(
            {
                "relationships": [
                    {
                        "from_document_id": "UU-13-2003",
                        "to_document_id": "UU-6-2023",
                        "relationship_type": "amended_by",
                        "confidence": "medium",
                        "notes": "Cipta Kerja.",
                    },
                    {
                        "from_document_id": "UNKNOWN-DOC",
                        "to_document_id": "OTHER-DOC",
                        "relationship_type": "amended_by",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    index = relationship_index_for_manifest(manifest)

    assert index.superseded_by["UU-13-2003"] == ["UU-6-2023"]
    assert index.superseded_by.get("UNKNOWN-DOC") == ["OTHER-DOC"]
