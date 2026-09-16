from app.services.answering.claim_verifier import (
    claim_coverage_score,
    verify_claims_deterministically,
)
from app.services.answering.generator import AnswerGenerator, _detect_language
from app.services.answering.memory_hardening import build_history_turns
from app.services.answering.prompts import MAX_CONTEXT_CHUNK_CHARS, render_user_prompt
from app.services.answering.schemas import Citation, GroundedClaim, HistoryTurn
from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.query import understand_query
from app.services.retrieval.schemas import RankedChunk, RetrievalDocument, RetrievalResponse


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
    assert response.prompt_version_id == "kerjapedia-grounded-answer-v7"
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
            "Pengusaha wajib membayar THR paling lambat tujuh hari sebelum hari raya keagamaan."
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


def _thr_formula_citation() -> Citation:
    return Citation(
        citation_id="cit_001",
        chunk_id="chunk-1",
        document_id="PERMENAKER-6-2016",
        document_title="Permenaker 6/2016",
        short_title="Permenaker 6/2016",
        legal_status="active",
        chapter=None,
        section=None,
        article="Pasal 3",
        paragraph="Ayat (1)",
        page_start=3,
        page_end=3,
        quote=(
            "Pekerja dengan masa kerja 12 (dua belas) bulan atau lebih "
            "diberikan 1 (satu) bulan upah; masa kerja kurang dari 12 bulan "
            "diberikan proporsional: masa kerja x 1 bulan upah dibagi 12."
        ),
        source_url="https://peraturan.bpk.go.id/",
        local_file=None,
        retrieval_score=0.9,
        rerank_score=0.9,
    )


def test_claim_verifier_excuses_query_numbers_but_flags_computed_result() -> None:
    claim = (
        "Untuk masa kerja 6 bulan, THR yang diterima adalah setengah bulan upah."
    )
    with_query = verify_claims_deterministically(
        [(claim, ["chunk-1"])],
        [_thr_formula_citation()],
        query="kalau 6 bulan kerja, berapa thr yang diterima?",
    )[0]

    assert with_query.supported is False
    assert "numbers_missing={0.5}" in with_query.support_detail
    assert ",6" not in with_query.support_detail
    assert "6," not in with_query.support_detail

    without_query = verify_claims_deterministically(
        [(claim, ["chunk-1"])],
        [_thr_formula_citation()],
    )[0]

    # "6" is excused via the cited PERMENAKER-6-2016 identifier even without
    # a query echo; only the computed "setengah" stays flagged.
    assert without_query.supported is False
    assert "numbers_missing={0.5}" in without_query.support_detail
    assert ",6" not in without_query.support_detail
    assert "6," not in without_query.support_detail


def test_claim_verifier_accepts_formula_with_literal_source_numbers() -> None:
    claims = verify_claims_deterministically(
        [
            (
                "THR dihitung proporsional: 6/12 x 1 bulan upah sesuai masa kerja.",
                ["chunk-1"],
            )
        ],
        [_thr_formula_citation()],
        query="kalau 6 bulan kerja, berapa thr yang diterima?",
    )

    assert claims[0].supported is True
    assert claims[0].support_detail.endswith("gates_ok")


def _uu_154a_citation() -> Citation:
    return Citation(
        citation_id="cit_154a",
        chunk_id="chunk-154a",
        document_id="UU-6-2023-47c5b9a46eebba4f75b0c13e",
        document_title="Undang-Undang Nomor 6 Tahun 2023",
        short_title="UU 6/2023",
        legal_status="active",
        chapter=None,
        section=None,
        article="Pasal 154A",
        paragraph="huruf b",
        page_start=40,
        page_end=40,
        quote=(
            "PHK karena efisiensi hanya dapat dilakukan jika perusahaan mengalami "
            "kerugian atau untuk mencegah kerugian."
        ),
        source_url="https://peraturan.bpk.go.id/",
        local_file=None,
        retrieval_score=0.9,
        rerank_score=0.9,
    )


def test_claim_verifier_excuses_citation_identifier_numbers() -> None:
    # Regression: the model names its source inline
    # ("... (UU-6-2023-... Pasal 154A huruf b)") while the quoted passage
    # omits the identifier digits. Those reference metadata, not inventions.
    claims = verify_claims_deterministically(
        [
            (
                "PHK karena efisiensi hanya dapat dilakukan jika perusahaan "
                "mengalami kerugian atau untuk mencegah kerugian "
                "(UU-6-2023-47c5b9a46eebba4f75b0c13e Pasal 154A huruf b).",
                ["chunk-154a"],
            )
        ],
        [_uu_154a_citation()],
        query="Apa syarat PHK karena efisiensi perusahaan?",
    )

    assert claims[0].supported is True
    assert claims[0].support_detail.endswith("gates_ok")


def test_claim_verifier_still_flags_numbers_absent_from_evidence_and_metadata() -> None:
    claims = verify_claims_deterministically(
        [
            (
                "PHK karena efisiensi wajib disertai pesangon 5 bulan upah "
                "(UU-6-2023 Pasal 154A huruf b).",
                ["chunk-154a"],
            )
        ],
        [_uu_154a_citation()],
        query="Apa syarat PHK karena efisiensi perusahaan?",
    )

    assert claims[0].supported is False
    assert "numbers_missing={5}" in claims[0].support_detail


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


def _ranked_chunk(chunk_id: str, text: str) -> RankedChunk:
    return RankedChunk(
        document=make_document(chunk_id, text, ["pkwt"], article="Pasal 15"),
        lexical_score=0.9,
        semantic_score=0.9,
        fusion_score=0.05,
        rerank_score=0.8,
        final_score=0.8,
        match_reasons=[],
    )


def _retrieval_with_chunks(texts: list[str]):
    engine = RetrievalEngine(
        documents=[
            make_document(f"chunk-{index}", text, ["pkwt"], article=f"Pasal {15 + index}")
            for index, text in enumerate(texts)
        ],
        top_k=len(texts),
    )
    return engine.search("Apakah pekerja PKWT memperoleh kompensasi?", top_k=len(texts))


def test_render_user_prompt_limits_context_to_selected_chunks() -> None:
    understanding = understand_query("Berapa kompensasi PKWT?")
    texts = [
        "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi.",
        "Ketentuan perhitungan kompensasi diatur lebih lanjut oleh menteri.",
        "Serikat pekerja berhak membuat perjanjian kerja bersama.",
        "Pengusaha wajib membayar upah tepat waktu setiap bulan.",
        "Waktu kerja lembur diatur dalam peraturan perusahaan.",
    ]
    retrieval = RetrievalResponse(
        query=understanding,
        results=[_ranked_chunk(f"chunk-{index}", text) for index, text in enumerate(texts)],
        warnings=[],
        should_refuse=False,
        refusal_reason=None,
    )
    selected = retrieval.results[:2]

    prompt = render_user_prompt("Berapa kompensasi PKWT?", retrieval, selected=selected)

    assert "[1]" in prompt and "[2]" in prompt
    assert "[3]" not in prompt
    assert "Waktu kerja lembur" not in prompt
    assert "hanya chunk ini yang boleh dikutip" in prompt


def test_render_user_prompt_truncates_long_chunks() -> None:
    long_text = "Ketentuan kompensasi PKWT berlaku. " * 200
    retrieval = _retrieval_with_chunks([long_text])

    prompt = render_user_prompt("Berapa kompensasi PKWT?", retrieval)

    assert len(long_text) > MAX_CONTEXT_CHUNK_CHARS
    assert long_text not in prompt
    assert prompt.count("Konteks terpilih") == 1


def test_render_user_prompt_renders_history_and_collapses_without_it() -> None:
    retrieval = _retrieval_with_chunks(["Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi."])

    without_history = render_user_prompt("Berapa besarnya?", retrieval)
    assert "Riwayat percakapan" not in without_history

    with_history = render_user_prompt(
        "Kalau kontraknya dua tahun?",
        retrieval,
        history=(
            HistoryTurn(
                question="Apakah pekerja PKWT mendapat kompensasi?",
                answer="Pekerja PKWT berhak memperoleh uang kompensasi.",
            ),
        ),
    )
    assert "Riwayat percakapan" in with_history
    assert "Apakah pekerja PKWT mendapat kompensasi?" in with_history
    assert "berhak memperoleh uang kompensasi" in with_history

    many_turns = tuple(
        HistoryTurn(question=f"Pertanyaan {index}?", answer=f"Jawaban {index}.")
        for index in range(4)
    )
    capped = render_user_prompt("Lanjut?", retrieval, history=many_turns)
    assert "Pertanyaan 0?" not in capped
    assert "Pertanyaan 3?" in capped


def test_base_generator_accepts_history_for_interface_parity() -> None:
    retrieval = _retrieval_with_chunks(["Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi."])

    response = AnswerGenerator().generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval,
        history=(HistoryTurn(question="Apa itu PKWT?", answer="Perjanjian Kerja Waktu Tertentu."),),
    )

    assert response.refusal_reason is None
    assert response.debug["history_turns"] == 1


def test_build_history_turns_collects_only_answered_cited_turns() -> None:
    def user(content: str) -> dict:
        return {"role": "user", "content": content, "message_id": "u-1"}

    def assistant(content: str, *, answered: bool = True) -> dict:
        return {
            "role": "assistant",
            "content": content,
            "metadata": {
                "answer": {
                    "answer_status": "answered" if answered else "refused",
                    "refusal_reason": None if answered else "insufficient_context",
                    "citations": [{"chunk_id": "chunk-1"}] if answered else [],
                }
            },
        }

    messages = [
        user("Apakah pekerja PKWT mendapat kompensasi?"),
        assistant("Pekerja PKWT berhak memperoleh uang kompensasi."),
        user("Rahasia yang tidak ada jawabannya"),
        assistant("Informasi tidak ditemukan.", answered=False),
        user("Kapan dibayar?"),
        assistant("Kompensasi dibayar saat kontrak berakhir."),
    ]

    turns = build_history_turns(messages)

    assert len(turns) == 2
    assert turns[0].question == "Apakah pekerja PKWT mendapat kompensasi?"
    assert turns[1].answer == "Kompensasi dibayar saat kontrak berakhir."


def test_build_history_turns_skips_turns_containing_sensitive_data() -> None:
    messages = [
        {"role": "user", "content": "Gaji saya 5000000, hubungi 081234567890 ya"},
        {
            "role": "assistant",
            "content": "Aturan pengupahan berlaku umum.",
            "metadata": {
                "answer": {
                    "answer_status": "answered",
                    "citations": [{"chunk_id": "chunk-1"}],
                }
            },
        },
    ]

    assert build_history_turns(messages) == ()
