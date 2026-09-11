from app.services.answering.claim_verifier import (
    claim_coverage_score,
    verify_claims_deterministically,
)
from app.services.answering.generator import AnswerGenerator, _detect_language
from app.services.answering.schemas import Citation, GroundedClaim
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
    assert response.prompt_version_id == "kerjapedia-grounded-answer-v5"
    assert "\n-" not in response.answer
    assert "cit_001" not in response.answer
    assert "PP 35/2021" in response.answer
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


def test_indonesian_language_detection_handles_siapa_and_payment_follow_up() -> None:
    assert _detect_language("Siapa yang menerima dendanya?") == "id"
    assert _detect_language("Dibayar kepada siapa?") == "id"
    assert _detect_language("Pembayaran kompensasi") == "id"
    assert _detect_language("THR payment deadline") == "en"


def test_claim_verifier_rejects_claim_without_supporting_citation() -> None:
    citation = Citation(
        citation_id="cit_001",
        chunk_id="chunk-1",
        document_id="PERMENAKER-6-2016",
        document_title="Permenaker 6/2016",
        short_title="Permenaker 6/2016",
        legal_status="active",
        chapter=None,
        section=None,
        article="Pasal 5",
        paragraph=None,
        page_start=1,
        page_end=1,
        quote="THR dibayarkan paling lambat tujuh hari sebelum hari raya.",
        source_url="https://peraturan.bpk.go.id/",
        local_file=None,
        retrieval_score=0.9,
        rerank_score=0.9,
    )

    claims = verify_claims_deterministically(
        [("Denda dibayarkan kepada pemerintah daerah.", ["chunk-1"])],
        [citation],
    )

    assert claims[0].supported is False


def test_claim_verifier_relinks_to_better_retrieved_evidence() -> None:
    unrelated = Citation(
        citation_id="cit_001",
        chunk_id="chunk-unrelated",
        document_id="PERMENAKER-6-2016",
        document_title="Permenaker 6/2016",
        short_title="Permenaker 6/2016",
        legal_status="active",
        chapter=None,
        section=None,
        article="Pasal 7",
        paragraph=None,
        page_start=7,
        page_end=7,
        quote="Pekerja dengan hubungan kerja tertentu tetap berhak atas THR.",
        source_url="https://peraturan.bpk.go.id/",
        local_file=None,
        retrieval_score=0.8,
        rerank_score=0.8,
    )
    supporting = Citation(
        citation_id="cit_002",
        chunk_id="chunk-deadline",
        document_id="PERMENAKER-6-2016",
        document_title="Permenaker 6/2016",
        short_title="Permenaker 6/2016",
        legal_status="active",
        chapter=None,
        section=None,
        article="Pasal 5",
        paragraph="Ayat (4)",
        page_start=5,
        page_end=5,
        quote=(
            "THR Keagamaan wajib dibayarkan oleh Pengusaha paling lambat "
            "7 (tujuh) hari sebelum Hari Raya Keagamaan."
        ),
        source_url="https://peraturan.bpk.go.id/",
        local_file=None,
        retrieval_score=0.95,
        rerank_score=0.95,
    )

    claims = verify_claims_deterministically(
        [
            (
                "THR Keagamaan wajib dibayarkan paling lambat 7 (tujuh) hari "
                "sebelum Hari Raya Keagamaan.",
                ["chunk-unrelated"],
            )
        ],
        [unrelated, supporting],
    )

    assert claims[0].supported is True
    assert claims[0].cited_chunk_ids == ["chunk-deadline"]
    assert claims[0].support_score == 1.0


def test_claim_verifier_normalizes_indonesian_legal_paraphrases() -> None:
    citation = Citation(
        citation_id="cit_001",
        chunk_id="chunk-1",
        document_id="PP-35-2021",
        document_title="PP 35/2021",
        short_title="PP 35/2021",
        legal_status="active",
        chapter=None,
        section=None,
        article="Pasal 36",
        paragraph=None,
        page_start=1,
        page_end=1,
        quote=(
            "Pemutusan Hubungan Kerja dapat terjadi karena Perusahaan melakukan efisiensi "
            "diikuti dengan penutupan Perusahaan atau tidak diikuti dengan penutupan "
            "Perusahaan yang disebabkan Perusahaan mengalami kerugian."
        ),
        source_url="https://peraturan.bpk.go.id/",
        local_file=None,
        retrieval_score=0.9,
        rerank_score=0.9,
    )

    claims = verify_claims_deterministically(
        [
            (
                "PHK karena efisiensi dapat dilakukan bila perusahaan mengalami kerugian, "
                "baik dengan atau tanpa penutupan perusahaan.",
                ["chunk-1"],
            )
        ],
        [citation],
    )

    assert claims[0].supported is True


def test_claim_verifier_rejects_unsupported_number_and_material_qualifier() -> None:
    citation = Citation(
        citation_id="cit_001",
        chunk_id="chunk-1",
        document_id="PP-35-2021",
        document_title="PP 35/2021",
        short_title="PP 35/2021",
        legal_status="active",
        chapter=None,
        section=None,
        article="Pasal 43",
        paragraph=None,
        page_start=1,
        page_end=1,
        quote="Pekerja berhak atas uang pesangon sebesar 0,5 kali ketentuan Pasal 40.",
        source_url="https://peraturan.bpk.go.id/",
        local_file=None,
        retrieval_score=0.9,
        rerank_score=0.9,
    )

    claims = verify_claims_deterministically(
        [
            (
                "Pekerja berhak atas pesangon sebesar 1 kali ketentuan Pasal 40.",
                ["chunk-1"],
            ),
            (
                "Pekerja berhak atas pesangon berkelanjutan sebesar 0,5 kali Pasal 40.",
                ["chunk-1"],
            ),
        ],
        [citation],
    )

    assert [claim.supported for claim in claims] == [False, False]


def test_claim_verifier_matches_spelled_out_indonesian_numbers() -> None:
    citation = Citation(
        citation_id="cit_001",
        chunk_id="chunk-1",
        document_id="PERMENAKER-6-2016",
        document_title="Permenaker 6/2016",
        short_title="Permenaker 6/2016",
        legal_status="active",
        chapter=None,
        section=None,
        article="Pasal 5",
        paragraph=None,
        page_start=1,
        page_end=1,
        quote=(
            "Pengusaha wajib membayar THR paling lambat tujuh hari "
            "sebelum hari raya keagamaan."
        ),
        source_url="https://peraturan.bpk.go.id/",
        local_file=None,
        retrieval_score=0.9,
        rerank_score=0.9,
    )

    claims = verify_claims_deterministically(
        [
            (
                "Batas waktu pembayaran THR adalah paling lambat 7 hari "
                "sebelum hari raya keagamaan.",
                ["chunk-1"],
            )
        ],
        [citation],
    )

    assert claims[0].supported is True


def test_claim_support_threshold_accepts_true_paraphrase() -> None:
    from app.services.answering.claim_verifier import _is_supported

    assert _is_supported(["chunk-1"], 0.40, True, True) is True
    assert _is_supported(["chunk-1"], 0.34, True, True) is False
    assert _is_supported(["chunk-1"], 0.90, False, True) is False
    assert _is_supported(["chunk-1"], 0.90, True, False) is False
    assert _is_supported([], 0.90, True, True) is False


def test_claim_coverage_detects_omitted_answer_claims() -> None:
    claims = [
        GroundedClaim(
            text="THR dibayar tujuh hari sebelum hari raya.",
            cited_chunk_ids=["chunk-1"],
            supported=True,
            support_score=0.95,
        )
    ]

    score = claim_coverage_score(
        "THR dibayar tujuh hari sebelum hari raya. Denda dibayarkan kepada pemerintah.",
        claims,
    )

    assert score < 0.75


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
