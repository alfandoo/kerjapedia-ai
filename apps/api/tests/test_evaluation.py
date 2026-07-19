from pathlib import Path

from app.services.answering.schemas import AnswerResponse, Citation
from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.metrics import (
    citation_correctness,
    faithfulness,
    recall_at_k,
    reciprocal_rank,
)
from app.services.evaluation.runner import EXPERIMENT_MODES, run_experiment, run_experiments
from app.services.evaluation.schemas import EvaluationQuestion
from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.schemas import RetrievalDocument


def golden_dataset_path() -> Path:
    return Path(__file__).resolve().parents[3] / "evaluation" / "golden_questions.json"


def make_document(
    chunk_id: str,
    document_id: str,
    text: str,
    topics: list[str],
    article: str,
) -> RetrievalDocument:
    provider = HashEmbeddingProvider()
    return RetrievalDocument(
        chunk_id=chunk_id,
        document_id=document_id,
        text=text,
        chapter=None,
        section=None,
        article=article,
        paragraph=None,
        page_start=1,
        page_end=1,
        token_count=len(text.split()),
        topics=topics,
        legal_status="active",
        source_url="https://peraturan.bpk.go.id/",
        embedding_model=provider.model_name,
        embedding=provider.embed([text])[0],
        metadata={
            "title": document_id,
            "short_title": document_id,
            "year": 2021,
            "regulation_type": "PP",
        },
    )


def test_golden_dataset_has_prd_distribution_and_hard_negatives() -> None:
    metadata, questions = load_evaluation_dataset(golden_dataset_path())

    assert len(questions) == 150
    assert metadata["distribution"] == {
        "pkwt": 15,
        "phk_pesangon": 25,
        "alih_daya": 10,
        "waktu_kerja": 10,
        "pengupahan": 20,
        "thr": 15,
        "bpjs_jkp": 20,
        "k3": 15,
        "hubungan_industrial": 15,
        "refusal": 5,
    }
    assert sum(question.hard_negative for question in questions) >= 10
    assert sum(question.should_refuse for question in questions) == 5
    assert all(question.expected_answer for question in questions)


def test_evaluation_metrics_are_deterministic() -> None:
    citation = Citation(
        citation_id="cit-1",
        chunk_id="chunk-1",
        document_id="PP-35-2021",
        document_title="PP 35/2021",
        short_title="PP 35/2021",
        legal_status="active",
        chapter=None,
        section=None,
        article="Pasal 15",
        paragraph=None,
        page_start=1,
        page_end=1,
        quote="Pekerja PKWT berhak memperoleh uang kompensasi saat perjanjian berakhir.",
        source_url="https://peraturan.bpk.go.id/",
        local_file=None,
        retrieval_score=0.9,
        rerank_score=0.9,
    )
    answer = AnswerResponse(
        query="Apakah pekerja PKWT mendapat kompensasi?",
        answer="Pekerja PKWT berhak memperoleh uang kompensasi saat perjanjian berakhir.",
        citations=[citation],
        confidence=0.9,
        related_documents=[],
        refusal_reason=None,
        clarification_question=None,
        disclaimer="Disclaimer",
        prompt_version_id="test",
        retrieved_chunk_ids=["chunk-1"],
    )

    assert recall_at_k(["PP-35-2021", "UU-6-2023"], ["PP-35-2021"], 5) == 0.5
    assert reciprocal_rank(["PP-35-2021"], ["UU-6-2023", "PP-35-2021"]) == 0.5
    assert citation_correctness(answer, ["PP-35-2021"], ["Pasal 15"]) == 1.0
    assert faithfulness(answer) == 1.0


def test_rag_regression_recall_and_mrr_by_core_topic() -> None:
    documents = [
        make_document(
            "pkwt-1",
            "PP-35-2021",
            "Pasal 15 pekerja PKWT memperoleh uang kompensasi saat kontrak berakhir.",
            ["pkwt", "kompensasi"],
            "Pasal 15",
        ),
        make_document(
            "phk-1",
            "PP-35-2021",
            "Pekerja yang terkena PHK memperoleh pesangon dan penggantian hak.",
            ["phk", "pesangon"],
            "Pasal 40",
        ),
        make_document(
            "thr-1",
            "PERMENAKER-6-2016",
            "THR dibayarkan paling lambat tujuh hari sebelum hari raya keagamaan.",
            ["thr"],
            "Pasal 5",
        ),
        make_document(
            "bpjs-1",
            "PP-37-2021",
            "JKP memberi manfaat bagi peserta BPJS yang kehilangan pekerjaan karena PHK.",
            ["bpjs", "jkp"],
            "Ketentuan manfaat JKP",
        ),
        make_document(
            "k3-1",
            "UU-1-1970",
            "Pengusaha wajib menyediakan perlindungan keselamatan dan kesehatan kerja K3.",
            ["k3"],
            "Ketentuan keselamatan kerja",
        ),
    ]
    questions = [
        EvaluationQuestion(
            "REG-PKWT",
            "pkwt",
            "Apakah pekerja PKWT mendapat kompensasi?",
            "Ya.",
            ["PP-35-2021"],
            ["Pasal 15"],
            ["pkwt"],
            False,
        ),
        EvaluationQuestion(
            "REG-PHK",
            "phk_pesangon",
            "Apa hak pesangon pekerja saat PHK?",
            "Ada hak akibat PHK.",
            ["PP-35-2021"],
            ["Pasal 40"],
            ["phk"],
            False,
        ),
        EvaluationQuestion(
            "REG-THR",
            "thr",
            "Kapan THR wajib dibayar?",
            "Tujuh hari sebelum hari raya.",
            ["PERMENAKER-6-2016"],
            ["Pasal 5"],
            ["thr"],
            False,
        ),
        EvaluationQuestion(
            "REG-BPJS",
            "bpjs_jkp",
            "Apa manfaat JKP BPJS setelah PHK?",
            "Manfaat JKP.",
            ["PP-37-2021"],
            ["Ketentuan manfaat JKP"],
            ["bpjs", "jkp"],
            False,
        ),
        EvaluationQuestion(
            "REG-K3",
            "k3",
            "Apa kewajiban pengusaha terkait K3?",
            "Perlindungan K3.",
            ["UU-1-1970"],
            ["Ketentuan keselamatan kerja"],
            ["k3"],
            False,
        ),
    ]

    report = run_experiment(questions, documents, "rerank", top_k=5)

    assert report.metrics.recall_at_5 >= 0.8
    assert report.metrics.mean_reciprocal_rank >= 0.8
    assert set(report.per_topic) == {"pkwt", "phk_pesangon", "thr", "bpjs_jkp", "k3"}


def test_experiment_comparison_contains_all_modes() -> None:
    documents = [
        make_document(
            "pkwt-1",
            "PP-35-2021",
            "Pekerja PKWT berhak memperoleh kompensasi.",
            ["pkwt"],
            "Pasal 15",
        )
    ]
    questions = [
        EvaluationQuestion(
            "EXP-001",
            "pkwt",
            "Apakah pekerja PKWT memperoleh kompensasi?",
            "Pekerja PKWT memperoleh kompensasi.",
            ["PP-35-2021"],
            ["Pasal 15"],
            ["pkwt"],
            False,
        )
    ]

    report = run_experiments(questions, documents)

    assert [item["mode"] for item in report["experiments"]] == list(EXPERIMENT_MODES)
    assert all("citation_correctness" in item["metrics"] for item in report["experiments"])
