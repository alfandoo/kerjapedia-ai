"""Semantic evaluation harness for answer quality assessment.

Loads golden questions, generates answers using the extractive AnswerGenerator,
and evaluates citation correctness, faithfulness, and claim support.

Usage:
    python evaluation/semantic_eval.py --dataset evaluation/golden_questions.json --top-k 5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from statistics import mean

# Add apps/api to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from app.services.answering.generator import AnswerGenerator
from app.services.answering.schemas import AnswerResponse
from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.metrics import (
    citation_correctness,
    faithfulness,
    recall_at_k,
    reciprocal_rank,
    unsupported_claim_rate,
)
from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.schemas import RetrievalDocument, RetrievalResponse


def _make_realistic_document(
    document_id: str,
    provider: HashEmbeddingProvider,
) -> RetrievalDocument:
    """Create a realistic RetrievalDocument with actual legal content."""
    # Simulate real legal document content
    content_map = {
        "PP-35-2021": {
            "text": "Pasal 15 Pekerja dengan PKWT berhak memperoleh uang kompensasi "
                    "pada akhir masa kerja. Besaran kompensasi sesuai masa kerja "
                    "minimal 1 bulan upah.",
            "chapter": "BAB II",
            "section": "Kompensasi",
            "article": "Pasal 15",
            "topics": ["pkwt", "kompensasi"],
        },
        "PP-35-2021-2": {
            "text": "Pasal 6 Masa kerja PKWT paling lama 5 tahun berdasarkan "
                    "jenis pekerjaan tertentu.",
            "chapter": "BAB I",
            "section": "Ketentuan Umum",
            "article": "Pasal 6",
            "topics": ["pkwt", "jangka_waktu"],
        },
        "UU-13-2003": {
            "text": "Pasal 151 Pekerja yang mengundurkan diri atau di PHK berhak "
                    "memperoleh pesangon sesuai ketentuan.",
            "chapter": "BAB VII",
            "section": "PHK",
            "article": "Pasal 151",
            "topics": ["phk", "pesangon"],
        },
        "UU-13-2003-2": {
            "text": "Pasal 36 Pengusaha melakukan PHK karena efisiensi perusahaan "
                    "mengalami kerugian berkepanjangan.",
            "chapter": "BAB V",
            "section": "Pemutusan Hubungan Kerja",
            "article": "Pasal 36",
            "topics": ["phk", "efisiensi"],
        },
        "UU-6-2023": {
            "text": "Pasal 81 Program Jaminan Kehilangan Pekerjaan memberikan "
                    "manfaat berupa uang dan akses informasi kerja.",
            "chapter": "BAB XI",
            "section": "JKP",
            "article": "Pasal 81",
            "topics": ["bpjs", "jkp"],
        },
        "PERMENAKER-6-2016": {
            "text": "Pasal 5 THR dibayarkan paling lambat 7 hari sebelum hari raya "
                    "kepada pekerja yang sudah berhak menerimanya.",
            "chapter": "BAB III",
            "section": "Waktu Pembayaran",
            "article": "Pasal 5",
            "topics": ["thr", "pembayaran"],
        },
        "UU-2-2004": {
            "text": "Pasal 4 Serikat pekerja berhak melakukan perundingan bersama "
                    "dengan pengusaha tentang ketentuan kerja.",
            "chapter": "BAB II",
            "section": "Hak Berserikat",
            "article": "Pasal 4",
            "topics": ["serikat_pekerja", "hubungan_industrial"],
        },
        "PP-50-2012": {
            "text": "Pasal 3 Pengusaha wajib mendaftarkan pekerja dalam program "
                    "jaminan sosial ketenagakerjaan BPJS.",
            "chapter": "BAB II",
            "section": "Kewajiban",
            "article": "Pasal 3",
            "topics": ["bpjs", "jaminan_sosial"],
        },
        "UU-1-1970": {
            "text": "Pasal 2 Setiap pekerja berhak atas keselamatan dan kesehatan "
                    "kerja di tempat kerja.",
            "chapter": "BAB I",
            "section": "Hak Pekerja",
            "article": "Pasal 2",
            "topics": ["k3", "keselamatan_kerja"],
        },
        "PP-36-2021": {
            "text": "Pasal 10 Upah minimum ditetapkan berdasarkan kebutuhan hidup "
                    "layak dan pertimbangan produktivitas.",
            "chapter": "BAB III",
            "section": "Upah Minimum",
            "article": "Pasal 10",
            "topics": ["pengupahan", "upah_minimum"],
        },
        "PP-51-2023": {
            "text": "Pasal 5 Pengupahan diatur dalam peraturan pemerintah ini "
                    "sebagai pengganti PP 36/2021.",
            "chapter": "BAB II",
            "section": "Ketentuan Pengupahan",
            "article": "Pasal 5",
            "topics": ["pengupahan"],
        },
        "UU-24-2011": {
            "text": "Pasal 1 Jaminan sosial bersifat nasional untuk melindungi "
                    "seluruh rakyat Indonesia.",
            "chapter": "BAB I",
            "section": "Ketentuan Umum",
            "article": "Pasal 1",
            "topics": ["jaminan_sosial"],
        },
        "UU-21-2000": {
            "text": "Pasal 3 Serikat pekerja berkewajiban menjaga kepentingan "
                    "anggota dan memperjuangkan kesejahteraan.",
            "chapter": "BAB II",
            "section": "Kewajiban",
            "article": "Pasal 3",
            "topics": ["serikat_pekerja"],
        },
        "PP-49-2025": {
            "text": "Pasal 7 Tunjangan hari raya diberikan kepada pekerja yang "
                    "telah bekerja minimal 12 bulan.",
            "chapter": "BAB II",
            "section": "Syarat Pemberian",
            "article": "Pasal 7",
            "topics": ["thr", "syarat"],
        },
        "PP-6-2025": {
            "text": "Pasal 10 Manfaat JKP meliputi uang tunai dan bantuan "
                    "pencarian kerja selama 6 bulan.",
            "chapter": "BAB III",
            "section": "Manfaat",
            "article": "Pasal 10",
            "topics": ["bpjs", "jkp", "manfaat"],
        },
        "PP-37-2021": {
            "text": "Pasal 8 Waktu kerja normal paling lama 8 jam sehari atau "
                    "40 jam seminggu.",
            "chapter": "BAB II",
            "section": "Waktu Kerja",
            "article": "Pasal 8",
            "topics": ["waktu_kerja"],
        },
    }

    info = content_map.get(document_id, {
        "text": f"Dokumen hukum {document_id} mengatur ketentuan ketenagakerjaan.",
        "chapter": None,
        "section": None,
        "article": None,
        "topics": [],
    })

    embedding = provider.embed([info["text"]])[0]
    return RetrievalDocument(
        chunk_id=f"{document_id}::chunk-1",
        document_id=document_id,
        text=info["text"],
        chapter=info.get("chapter"),
        section=info.get("section"),
        article=info.get("article"),
        paragraph=None,
        page_start=1,
        page_end=2,
        token_count=len(info["text"].split()),
        topics=info.get("topics", []),
        legal_status="active",
        source_url="",
        embedding=embedding,
        metadata={},
    )


def _text_overlap_score(text_a: str, text_b: str) -> float:
    """Compute token overlap between two texts."""
    tokens_a = set(re.findall(r"[a-z0-9]+", text_a.lower()))
    tokens_b = set(re.findall(r"[a-z0-9]+", text_b.lower()))
    if not tokens_a:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a)


def run_semantic_evaluation(
    dataset_path: Path,
    top_k: int = 5,
) -> dict:
    """Run semantic evaluation on golden questions."""
    metadata, questions = load_evaluation_dataset(dataset_path)
    provider = HashEmbeddingProvider()

    # Collect all unique document IDs
    all_doc_ids = set()
    for q in questions:
        all_doc_ids.update(q.expected_document_ids)

    # Create realistic documents
    documents = [_make_realistic_document(doc_id, provider) for doc_id in sorted(all_doc_ids)]

    # Build retrieval engine and answer generator
    engine = RetrievalEngine(documents=documents, top_k=max(top_k, len(documents)))
    generator = AnswerGenerator()

    results = []
    for question in questions:
        # Retrieve
        retrieval = engine.search(question.question, top_k=max(top_k, len(documents)))

        # Generate answer
        answer = generator.generate(question.question, retrieval)

        # Compute metrics
        retrieved_ids = list(dict.fromkeys(
            r.document.document_id for r in retrieval.results
        ))[:top_k]

        if question.should_refuse:
            results.append({
                "question_id": question.question_id,
                "category": question.category,
                "should_refuse": True,
                "refused": retrieval.should_refuse,
                "answer_length": len(answer.answer) if answer.answer else 0,
                "citation_count": len(answer.citations),
                "claim_count": len(answer.claims),
                "recall_at_k": None,
                "reciprocal_rank": None,
                "citation_correctness": None,
                "faithfulness": None,
                "unsupported_claim_rate": None,
            })
        else:
            r5 = recall_at_k(question.expected_document_ids, retrieved_ids, 5)
            rr = reciprocal_rank(question.expected_document_ids, retrieved_ids)
            c_correct = citation_correctness(
                answer, question.expected_document_ids, question.expected_articles
            )
            f_score = faithfulness(answer)
            ucr = unsupported_claim_rate(answer)

            results.append({
                "question_id": question.question_id,
                "category": question.category,
                "should_refuse": False,
                "refused": retrieval.should_refuse,
                "answer_length": len(answer.answer) if answer.answer else 0,
                "citation_count": len(answer.citations),
                "claim_count": len(answer.claims),
                "retrieved_ids": retrieved_ids,
                "expected_ids": question.expected_document_ids,
                "recall_at_k": r5,
                "reciprocal_rank": rr,
                "citation_correctness": c_correct,
                "faithfulness": f_score,
                "unsupported_claim_rate": ucr,
                "answer_preview": answer.answer[:200] if answer.answer else "",
            })

    # Aggregate metrics
    answerable = [r for r in results if not r["should_refuse"]]
    refusal = [r for r in results if r["should_refuse"]]

    recall_values = [r["recall_at_k"] for r in answerable if r["recall_at_k"] is not None]
    rr_values = [r["reciprocal_rank"] for r in answerable if r["reciprocal_rank"] is not None]
    citation_values = [r["citation_correctness"] for r in answerable if r["citation_correctness"] is not None]
    faith_values = [r["faithfulness"] for r in answerable if r["faithfulness"] is not None]
    ucr_values = [r["unsupported_claim_rate"] for r in answerable if r["unsupported_claim_rate"] is not None]

    # Per-category breakdown
    categories = {}
    for q in questions:
        cat = q.category
        if cat not in categories:
            categories[cat] = {
                "total": 0, "answerable": 0, "refusal": 0,
                "recalls": [], "rrs": [], "citations": [], "faith": [], "ucr": []
            }
        categories[cat]["total"] += 1
        if q.should_refuse:
            categories[cat]["refusal"] += 1
        else:
            categories[cat]["answerable"] += 1

    for r in results:
        cat = r["category"]
        if not r["should_refuse"]:
            if r["recall_at_k"] is not None:
                categories[cat]["recalls"].append(r["recall_at_k"])
            if r["reciprocal_rank"] is not None:
                categories[cat]["rrs"].append(r["reciprocal_rank"])
            if r["citation_correctness"] is not None:
                categories[cat]["citations"].append(r["citation_correctness"])
            if r["faithfulness"] is not None:
                categories[cat]["faith"].append(r["faithfulness"])
            if r["unsupported_claim_rate"] is not None:
                categories[cat]["ucr"].append(r["unsupported_claim_rate"])

    report = {
        "dataset": str(dataset_path),
        "question_count": len(questions),
        "answerable_count": len(answerable),
        "refusal_count": len(refusal),
        "top_k": top_k,
        "overall": {
            "recall_at_k": round(mean(recall_values), 4) if recall_values else 0.0,
            "mean_reciprocal_rank": round(mean(rr_values), 4) if rr_values else 0.0,
            "citation_correctness": round(mean(citation_values), 4) if citation_values else 0.0,
            "faithfulness": round(mean(faith_values), 4) if faith_values else 0.0,
            "unsupported_claim_rate": round(mean(ucr_values), 4) if ucr_values else 0.0,
        },
        "per_category": {
            cat: {
                "total": info["total"],
                "answerable": info["answerable"],
                "refusal": info["refusal"],
                "recall_at_k": round(mean(info["recalls"]), 4) if info["recalls"] else None,
                "mean_reciprocal_rank": round(mean(info["rrs"]), 4) if info["rrs"] else None,
                "citation_correctness": round(mean(info["citations"]), 4) if info["citations"] else None,
                "faithfulness": round(mean(info["faith"]), 4) if info["faith"] else None,
                "unsupported_claim_rate": round(mean(info["ucr"]), 4) if info["ucr"] else None,
            }
            for cat, info in sorted(categories.items())
        },
        "questions": results,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run semantic evaluation on golden questions.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parent / "golden_questions.json",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = run_semantic_evaluation(args.dataset, args.top_k)

    output_path = args.output or args.dataset.parent / "semantic_eval_report.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Print summary
    print(f"Dataset: {report['question_count']} questions ({report['answerable_count']} answerable, {report['refusal_count']} refusal)")
    print(f"Top-K: {report['top_k']}")
    print()
    print("=== Overall Metrics ===")
    o = report["overall"]
    print(f"  Recall@{report['top_k']}:          {o['recall_at_k']:.2%}")
    print(f"  MRR:              {o['mean_reciprocal_rank']:.4f}")
    print(f"  Citation Correctness: {o['citation_correctness']:.2%}")
    print(f"  Faithfulness:     {o['faithfulness']:.2%}")
    print(f"  Unsupported Claim Rate: {o['unsupported_claim_rate']:.2%}")
    print()
    print("=== Per-Category Breakdown ===")
    for cat, info in report["per_category"].items():
        r = info["recall_at_k"]
        c = info["citation_correctness"]
        f = info["faithfulness"]
        r_str = f"{r:.2%}" if r is not None else "N/A"
        c_str = f"{c:.2%}" if c is not None else "N/A"
        f_str = f"{f:.2%}" if f is not None else "N/A"
        print(f"  {cat:25s}  R@5={r_str:6s}  Cite={c_str:6s}  Faith={f_str}")
    print(f"\nReport written to {output_path}")


if __name__ == "__main__":
    main()
