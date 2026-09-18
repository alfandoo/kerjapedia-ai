from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.services.answering.openrouter_generator import (
    OpenRouterAnswerGenerator,
    _clean_answer_text,
    _is_transient_provider_error,
)
from app.services.answering.schemas import HistoryTurn
from app.services.retrieval.schemas import RetrievalDocument, RetrievalResponse


def test_embed_queries_hybrid_falls_back_without_native_method() -> None:
    from app.services.ingestion.embeddings import (
        HashEmbeddingProvider,
        embed_hybrid,
        embed_queries_hybrid,
    )

    provider = HashEmbeddingProvider()

    assert embed_queries_hybrid(provider, ["kapan THR dibayar"]) == embed_hybrid(
        provider, ["kapan THR dibayar"]
    )


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
    from app.services.ingestion.embeddings import HashEmbeddingProvider
    from app.services.retrieval.engine import RetrievalEngine

    provider = HashEmbeddingProvider()
    text = "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi."
    document = RetrievalDocument(
        chunk_id="chunk-1",
        document_id="PP-35-2021",
        text=text,
        chapter=None,
        section=None,
        article="Pasal 15",
        paragraph="Ayat (1)",
        page_start=12,
        page_end=12,
        token_count=8,
        topics=["pkwt"],
        legal_status="active",
        source_url="https://peraturan.bpk.go.id/",
        embedding=provider.embed([text])[0],
        metadata={
            "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
            "short_title": "PP 35/2021",
        },
    )
    return RetrievalEngine(documents=[document]).search(
        "Apakah pekerja PKWT memperoleh kompensasi?", top_k=1
    )


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


def _transient_error(name: str, status_code: int) -> Exception:
    error_type = type(name, (Exception,), {"status_code": status_code})
    return error_type(f"upstream HTTP {status_code}")


def _valid_pkwt_payload() -> dict:
    return {
        "answer": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
        "cited_chunk_ids": ["chunk-1"],
        "claims": [
            {
                "text": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
                "cited_chunk_ids": ["chunk-1"],
            }
        ],
    }


def test_is_transient_provider_error_classifies_status_codes() -> None:
    assert _is_transient_provider_error(_transient_error("RateLimitError", 429)) is True
    assert _is_transient_provider_error(_transient_error("UpstreamError", 502)) is True
    assert _is_transient_provider_error(_transient_error("OverloadedError", 503)) is True
    assert _is_transient_provider_error(_transient_error("TimeoutError", 408)) is True
    assert _is_transient_provider_error(_transient_error("BadRequestError", 400)) is False
    assert _is_transient_provider_error(RuntimeError("boom")) is False


def test_openrouter_generator_retries_transient_rate_limit() -> None:
    client = FakeOpenRouterClient(
        [
            _transient_error("RateLimitError", 429),
            _valid_pkwt_payload(),
        ]
    )
    generator = OpenRouterAnswerGenerator(
        api_key="test-key",
        transient_backoff_seconds=0,
    )
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert client.calls == 2
    assert answer.debug["transient_retries"] == 1
    assert answer.debug["generation_attempts"] == 2


def test_openrouter_generator_backs_off_between_transient_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    client = FakeOpenRouterClient(
        [
            _transient_error("RateLimitError", 429),
            _transient_error("UpstreamError", 502),
            _valid_pkwt_payload(),
        ]
    )
    generator = OpenRouterAnswerGenerator(
        api_key="test-key",
        transient_backoff_seconds=2.0,
    )
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert client.calls == 3
    assert sleeps == [2.0, 4.0]
    assert answer.debug["transient_retries"] == 2


def test_openrouter_generator_gives_up_after_transient_budget() -> None:
    client = FakeOpenRouterClient(
        [
            _transient_error("RateLimitError", 429),
            _transient_error("UpstreamError", 502),
            _transient_error("OverloadedError", 503),
        ]
    )
    generator = OpenRouterAnswerGenerator(
        api_key="test-key",
        fail_closed=True,
        transient_max_retries=2,
        transient_backoff_seconds=0,
    )
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "temporarily_unavailable"
    assert answer.debug["failure_category"] == "provider_failure"
    assert answer.debug["transient_retries"] == 2
    assert client.calls == 3


def test_openrouter_generator_does_not_retry_permanent_errors() -> None:
    client = FakeOpenRouterClient(RuntimeError("provider unavailable"))
    generator = OpenRouterAnswerGenerator(
        api_key="test-key",
        fail_closed=True,
        transient_backoff_seconds=0,
    )
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "temporarily_unavailable"
    assert client.calls == 1
    assert answer.debug["transient_retries"] == 0


def test_openrouter_generator_sends_configured_fallback_models() -> None:
    fallbacks = ("google/gemma-4-31b-it:free", "nvidia/nemotron-3-super-120b-a12b:free")
    client = FakeOpenRouterClient(_valid_pkwt_payload())
    generator = OpenRouterAnswerGenerator(api_key="test-key", fallback_models=fallbacks)
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert client.requests[0]["extra_body"] == {"models": list(fallbacks)}


def test_openrouter_generator_omits_fallback_models_when_unconfigured() -> None:
    client = FakeOpenRouterClient(_valid_pkwt_payload())
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert "extra_body" not in client.requests[0]


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


def test_openrouter_generator_salvages_answer_with_missing_claims() -> None:
    payload = {
        "answer": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
        "cited_chunk_ids": ["chunk-1"],
        "claims": [],
    }
    client = FakeOpenRouterClient([payload, payload])
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert "answer_repaired_by_sentence_salvage" in answer.warnings
    assert "Maaf, jawaban terverifikasi" not in answer.answer
    assert "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15." in answer.answer
    assert answer.claims and all(claim.supported for claim in answer.claims)
    assert answer.debug["repair"] == "sentence_salvage"


def test_openrouter_generator_salvages_prose_without_json() -> None:
    prose = (
        "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15. "
        "Langit berwarna hijau."
    )
    client = FakeOpenRouterClient([prose, prose])
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert "answer_repaired_by_sentence_salvage" in answer.warnings
    assert "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15." in answer.answer
    assert "Langit berwarna hijau" not in answer.answer


def test_openrouter_generator_salvage_declines_unsupported_lead() -> None:
    prose = (
        "Langit berwarna hijau. "
        "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15."
    )
    client = FakeOpenRouterClient([prose, prose])
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert answer.debug.get("fallback") == "extractive"
    assert "answer_repaired_by_sentence_salvage" not in answer.warnings


def test_openrouter_generator_salvage_applies_under_fail_closed() -> None:
    payload = {
        "answer": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
        "cited_chunk_ids": ["chunk-1"],
        "claims": [],
    }
    client = FakeOpenRouterClient([payload, payload])
    generator = OpenRouterAnswerGenerator(api_key="test-key", fail_closed=True)
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert "answer_repaired_by_sentence_salvage" in answer.warnings


def _empty_retrieval(question: str):
    from app.services.retrieval.query import understand_query
    from app.services.retrieval.schemas import RetrievalResponse

    return RetrievalResponse(
        query=understand_query(question),
        results=[],
        warnings=[],
        should_refuse=False,
        refusal_reason=None,
    )


def test_openrouter_generator_requests_clarification_for_vague_question() -> None:
    # Longer than three tokens, no topic, no recognized intent: exercises the
    # branch that used to be dead because ["general_question"] is truthy.
    generator = OpenRouterAnswerGenerator(api_key="test-key")

    answer = generator.generate(
        "Tolong sampaikan aturan mainnya buat saya.",
        _empty_retrieval("Tolong sampaikan aturan mainnya buat saya."),
    )

    assert answer.answer_status == "clarification"
    assert answer.clarification_question


def test_openrouter_generator_skips_clarification_for_topical_question() -> None:
    generator = OpenRouterAnswerGenerator(api_key="test-key")

    assert (
        generator._needs_clarification(
            "Apakah pekerja PKWT memperoleh kompensasi?",
            _empty_retrieval("Apakah pekerja PKWT memperoleh kompensasi?"),
        )
        is False
    )


def test_openrouter_generator_falls_back_to_extractive_answer() -> None:
    client = FakeOpenRouterClient(["not-json", "still-not-json"])
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert "Maaf, jawaban terverifikasi" not in answer.answer
    assert "answer_degraded_extractive" in answer.warnings
    assert [citation.chunk_id for citation in answer.citations] == ["chunk-1"]
    assert answer.claims
    assert all(claim.supported for claim in answer.claims)
    assert all(claim.support_detail == "extractive_verbatim" for claim in answer.claims)
    assert "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi." in answer.answer
    assert "- **PP 35/2021, Pasal 15** — " in answer.answer
    assert answer.debug["fallback"] == "extractive"
    assert answer.debug["failure_category"] == "validation_failure"


def test_openrouter_generator_extractive_fallback_on_provider_failure() -> None:
    client = FakeOpenRouterClient(RuntimeError("provider unavailable"))
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "answered"
    assert "answer_degraded_extractive" in answer.warnings
    assert [citation.chunk_id for citation in answer.citations] == ["chunk-1"]
    assert answer.debug["failure_category"] == "provider_failure"


def test_openrouter_generator_extractive_respects_fail_closed() -> None:
    client = FakeOpenRouterClient(RuntimeError("provider unavailable"))
    generator = OpenRouterAnswerGenerator(api_key="test-key", fail_closed=True)
    generator._client = client

    answer = generator.generate(
        "Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval_response(),
    )

    assert answer.answer_status == "temporarily_unavailable"
    assert "answer_degraded_extractive" not in answer.warnings


def test_first_sentences_bounds_extractive_excerpts() -> None:
    from app.services.answering.openrouter_generator import _first_sentences

    quote = (
        "Kalimat pertama yang didukung. Kalimat kedua yang didukung. "
        "Kalimat ketiga yang seharusnya terpotong."
    )
    excerpt = _first_sentences(quote)
    assert "Kalimat pertama" in excerpt
    assert "Kalimat kedua" in excerpt
    assert "Kalimat ketiga" not in excerpt

    long_quote = "Kata " * 500
    assert len(_first_sentences(long_quote)) <= 601


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Apakah pekerja PKWT memperoleh kompensasi?", "jawaban terverifikasi"),
        ("Are fixed-term workers entitled to compensation?", "verified answer"),
    ],
)
def test_openrouter_provider_failure_is_localized(query: str, expected: str) -> None:
    generator = OpenRouterAnswerGenerator(api_key="test-key", fail_closed=True)
    generator._client = FakeOpenRouterClient(RuntimeError("provider unavailable"))

    answer = generator.generate(query, retrieval_response())

    assert answer.answer_status == "temporarily_unavailable"
    assert expected in answer.answer.lower()
    assert answer.debug["failure_category"] == "provider_failure"


def _three_chunk_retrieval() -> RetrievalResponse:
    from app.services.ingestion.embeddings import HashEmbeddingProvider
    from app.services.retrieval.engine import RetrievalEngine

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
    provider = HashEmbeddingProvider()
    documents = [
        RetrievalDocument(
            chunk_id=chunk_id,
            document_id="PP-35-2021",
            text=text,
            chapter=None,
            section=None,
            article=article,
            paragraph=None,
            page_start=12,
            page_end=12,
            token_count=8,
            topics=["pkwt"],
            legal_status="active",
            source_url="https://peraturan.bpk.go.id/",
            embedding=provider.embed([text])[0],
            metadata={
                "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
                "short_title": "PP 35/2021",
            },
        )
        for chunk_id, text, article in texts
    ]
    return RetrievalEngine(documents=documents).search(
        "Apakah pekerja PKWT memperoleh kompensasi?", top_k=3
    )


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
