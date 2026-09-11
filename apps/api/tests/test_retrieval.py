import json
from dataclasses import replace
from pathlib import Path

from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.pinecone_store import _hybrid_alpha
from app.services.retrieval.postprocessing import (
    apply_query_focus_adjustments,
    drop_heading_only_chunks,
    expand_context,
    is_heading_only,
)
from app.services.retrieval.query import is_employment_query, understand_query
from app.services.retrieval.relationships import (
    RegulationRelationship,
    build_relationship_index,
    relationship_index_for_manifest,
    relationship_snapshot_hash,
)
from app.services.retrieval.schemas import RankedChunk, RetrievalDocument
from app.services.retrieval.store import load_artifact_documents


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
        metadata={"year": 2021, "regulation_type": "PP", "number": 35},
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


def test_query_understanding_supports_english_and_hard_regulation_number() -> None:
    query = understand_query(
        "What compensation does a fixed-term worker receive under PP No. 35 of 2021?"
    )

    assert "pkwt" in query.detected_topics
    assert query.filters["regulation_type"] == "PP"
    assert query.filters["number"] == 35
    assert query.filters["year"] == 2021
    assert is_employment_query(query) is True


def test_query_understanding_preserves_manifest_regulation_type_casing() -> None:
    query = understand_query("Apa isi Permenaker No. 6 Tahun 2016 tentang THR?")

    assert query.filters["regulation_type"] == "Permenaker"
    assert query.filters["number"] == 6


def test_inferred_topic_is_a_soft_signal_not_a_hard_filter() -> None:
    query = understand_query("Apakah pekerja PKWT memperoleh kompensasi?")

    assert query.filters["inferred_topics"] == ["pkwt"]
    assert "topics" not in query.filters


def test_contextual_retrieval_inherits_document_scope_not_articles() -> None:
    query = understand_query(
        "dendanya bayar ke siapa?",
        retrieval_query=(
            "Kapan pembayaran THR menurut Pasal 5 Permenaker No. 6 Tahun 2016? "
            "dendanya bayar ke siapa?"
        ),
        context_topics=("thr",),
        context_document_ids=("PERMENAKER-6-2016",),
        context_articles=("Pasal 5",),
    )

    assert query.detected_topics == ["thr"]
    assert query.context_document_ids == ["PERMENAKER-6-2016"]
    assert query.context_articles == ["Pasal 5"]
    # The article is often the answer itself: never inherited from memory.
    assert "article" not in query.filters
    # The discussed document scope carries over to the follow-up.
    assert query.filters["regulation_type"] == "Permenaker"
    assert query.filters["number"] == 6
    assert query.filters["year"] == 2016


def test_context_inheritance_stops_on_topic_switch_or_ambiguity() -> None:
    switched = understand_query(
        "bagaimana dengan PHK?",
        context_topics=("thr",),
        context_document_ids=("PERMENAKER-6-2016",),
    )
    assert "regulation_type" not in switched.filters

    ambiguous = understand_query(
        "berapa besarnya?",
        context_topics=("thr",),
        context_document_ids=("PERMENAKER-6-2016", "PP-35-2021"),
    )
    assert "regulation_type" not in ambiguous.filters


def test_bare_year_is_not_a_hard_filter() -> None:
    query = understand_query("aturan yang berlaku sejak 2019?")

    assert "year" not in query.filters
    assert any("2019" in rewritten for rewritten in query.rewritten_queries)


def test_bare_berapa_detects_calculation_intent() -> None:
    query = understand_query("berapa kompensasi karyawan kontrak?")

    assert "calculation" in query.detected_intents
    assert "pkwt" in query.detected_topics
    assert any("uang kompensasi" in rewritten for rewritten in query.rewritten_queries)
    assert any("PP 35 Tahun 2021" in rewritten for rewritten in query.rewritten_queries)


def test_named_laws_resolve_to_filters() -> None:
    cipta = understand_query("apa itu cipta kerja?")

    assert cipta.filters["regulation_type"] == "UU"
    assert cipta.filters["number"] == 6
    assert cipta.filters["year"] == 2023

    explicit = understand_query("apa isi PP 35 Tahun 2021 tentang cipta kerja?")
    assert explicit.filters["regulation_type"] == "PP"
    assert explicit.filters["number"] == 35


def test_common_typos_normalize_before_understanding() -> None:
    query = understand_query("berapa kompenasasi karywan kontrak?")

    assert "pkwt" in query.detected_topics
    assert any("uang kompensasi" in rewritten for rewritten in query.rewritten_queries)


def test_original_question_keeps_its_own_hard_filters_with_context() -> None:
    query = understand_query(
        "Apa isi Pasal 10 Permenaker No. 6 Tahun 2016?",
        retrieval_query="Kapan THR dibayar? Apa isi Pasal 10 Permenaker No. 6 Tahun 2016?",
        context_articles=("Pasal 5",),
    )

    assert query.filters["article"] == "Pasal 10"
    assert query.filters["year"] == 2016
    assert query.filters["number"] == 6
    assert query.filters["regulation_type"] == "Permenaker"


def test_hybrid_alpha_prefers_sparse_signal_for_exact_legal_references() -> None:
    assert _hybrid_alpha("Apa isi Pasal 10 Permenaker 6 Tahun 2016?") == 0.35
    assert _hybrid_alpha("Bagaimana hak pekerja setelah kontrak berakhir?") == 0.65


def test_retrieval_refuses_query_outside_employment_scope() -> None:
    engine = RetrievalEngine(documents=[])

    response = engine.search("Berapa tarif pajak kendaraan?")

    assert response.should_refuse
    assert response.refusal_reason == "out_of_scope_query"
    assert response.results == []


def test_explicit_regulation_filter_never_falls_back_to_other_documents() -> None:
    engine = RetrievalEngine(
        documents=[
            make_document(
                "chunk-1",
                "Pasal 15 mengatur kompensasi PKWT.",
                ["pkwt"],
                article="Pasal 15",
            )
        ]
    )

    response = engine.search("Apa kompensasi PKWT menurut PP No. 99 Tahun 2021?")

    assert response.should_refuse is True
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


def ranked_chunk(document: RetrievalDocument, score: float) -> RankedChunk:
    return RankedChunk(
        document=document,
        lexical_score=score,
        semantic_score=score,
        fusion_score=score,
        rerank_score=score,
        final_score=score,
        match_reasons=[],
    )


def test_heading_only_chunks_do_not_displace_substantive_rules() -> None:
    heading = make_document("heading", "Bagian Kesatu Tata Cara Pembayaran", ["thr"])
    rule = make_document(
        "rule",
        "Pengusaha wajib membayarkan THR paling lambat tujuh hari sebelum hari raya.",
        ["thr"],
        article="Pasal 5",
    )

    filtered = drop_heading_only_chunks([ranked_chunk(heading, 0.9), ranked_chunk(rule, 0.8)])

    assert is_heading_only(heading) is True
    assert [item.document.chunk_id for item in filtered] == ["rule"]


def test_heading_only_filter_retains_last_available_context() -> None:
    heading = make_document("heading", "BAB II PENGUPAHAN", ["pengupahan"])

    filtered = drop_heading_only_chunks([ranked_chunk(heading, 0.9)])

    assert [item.document.chunk_id for item in filtered] == ["heading"]


def test_context_expansion_does_not_reintroduce_heading_only_chunks() -> None:
    heading = replace(
        make_document("heading", "Pasal 5", ["thr"], article="Pasal 5"),
        char_start=0,
    )
    rule = replace(
        make_document(
            "rule",
            "Pengusaha wajib membayarkan THR paling lambat tujuh hari sebelum hari raya.",
            ["thr"],
            article="Pasal 5",
        ),
        char_start=10,
    )

    expanded = expand_context([ranked_chunk(rule, 0.9)], [heading, rule])

    assert [item.document.chunk_id for item in expanded] == ["rule"]


def test_explicit_query_term_boosts_relevant_legal_chunks() -> None:
    unrelated = make_document(
        "unrelated",
        "Pekerja melakukan pelanggaran setelah menerima tiga surat peringatan.",
        ["phk"],
        article="Pasal 52",
    )
    efficiency_rule = make_document(
        "efficiency-rule",
        "Perusahaan melakukan efisiensi karena mengalami kerugian.",
        ["phk"],
        article="Pasal 36",
    )
    efficiency_rights = make_document(
        "efficiency-rights",
        "Pekerja yang terkena efisiensi berhak atas uang pesangon.",
        ["phk"],
        article="Pasal 43",
    )

    adjusted = apply_query_focus_adjustments(
        [
            ranked_chunk(unrelated, 0.75),
            ranked_chunk(efficiency_rule, 0.70),
            ranked_chunk(efficiency_rights, 0.65),
        ],
        "apa syarat phk karena efisiensi perusahaan",
    )

    assert adjusted[0].document.chunk_id == "efficiency-rule"
    assert "explicit_query_term:efisiensi" in adjusted[0].match_reasons


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


def test_relationship_snapshot_hash_is_order_independent_and_change_sensitive() -> None:
    from types import SimpleNamespace

    def row(relationship_id: str, notes: str):
        return SimpleNamespace(
            relationship_id=relationship_id,
            from_document_id="OLD",
            to_document_id="NEW",
            relationship_type="replaced_by",
            from_article=None,
            to_article=None,
            confidence="high",
            evidence_url="https://example.test/evidence",
            notes=notes,
            reviewed_by="reviewer-1",
            reviewed_at=None,
        )

    first = row("rel-1", "official evidence")
    second = row("rel-2", "supporting evidence")

    assert relationship_snapshot_hash([first, second]) == relationship_snapshot_hash(
        [second, first]
    )
    assert relationship_snapshot_hash([first]) != relationship_snapshot_hash(
        [row("rel-1", "changed evidence")]
    )


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

    old_ranked = next(item for item in response.results if item.document.chunk_id == "old-chunk")
    old_baseline = next(item for item in baseline.results if item.document.chunk_id == "old-chunk")
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


def _write_build_artifact(root: Path, build_id: str, text: str) -> None:
    base = root / "documents" / "PP-35-2021" / "v1" / "builds" / build_id
    processed = base / "processed"
    metadata = base / "metadata"
    processed.mkdir(parents=True)
    metadata.mkdir(parents=True)
    chunk_id = f"{build_id}-chunk"
    chunk = {
        "chunk_id": chunk_id,
        "document_id": "PP-35-2021",
        "chapter": "BAB II",
        "section": None,
        "article": "Pasal 15",
        "paragraph": "Ayat (1)",
        "page_start": 1,
        "page_end": 1,
        "text": text,
        "retrieval_text": f"PP 35/2021\nPasal 15\n{text}",
        "token_count": 8,
        "topics": ["pkwt"],
        "legal_status": "active",
        "source_url": "https://peraturan.bpk.go.id/Details/161904/pp-no-35-tahun-2021",
        "build_id": build_id,
    }
    (processed / "chunks.json").write_text(json.dumps([chunk]), encoding="utf-8")
    (processed / "embeddings.json").write_text(
        json.dumps(
            [
                {
                    "chunk_id": chunk_id,
                    "embedding_model": "BAAI/bge-m3",
                    "embedding": [1.0, 0.0],
                    "sparse_embedding": {"1": 1.0},
                }
            ]
        ),
        encoding="utf-8",
    )
    (metadata / "document.json").write_text(
        json.dumps({"document_id": "PP-35-2021"}),
        encoding="utf-8",
    )


def test_artifact_loader_selects_the_release_build_not_latest_directory(
    tmp_path: Path,
) -> None:
    _write_build_artifact(tmp_path, "build-old", "artefak lama")
    _write_build_artifact(tmp_path, "build-approved", "artefak approved")

    documents = load_artifact_documents(
        tmp_path,
        {"PP-35-2021": 1},
        {"PP-35-2021-v1": "build-approved"},
    )

    assert len(documents) == 1
    assert documents[0].build_id == "build-approved"
    assert documents[0].text == "artefak approved"
    assert documents[0].retrieval_text.startswith("PP 35/2021")
