"""Standalone retrieval metrics harness for offline evaluation.

Loads golden questions, creates synthetic documents for expected_document_ids,
and runs retrieval evaluation using the in-memory RetrievalEngine.

Usage:
    python evaluation/retrieval_metrics.py --dataset evaluation/golden_questions.json --top-k 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

# Add apps/api to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.metrics import ndcg_at_k, recall_at_k, reciprocal_rank
from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.schemas import RetrievalDocument


def _make_synthetic_document(
    document_id: str,
    provider: HashEmbeddingProvider,
) -> RetrievalDocument:
    """Create a synthetic RetrievalDocument for a given document_id."""
    text = f"Dokumen hukum {document_id} mengatur ketentuan ketenagakerjaan."
    embedding = provider.embed([text])[0]
    return RetrievalDocument(
        chunk_id=f"{document_id}::synth-1",
        document_id=document_id,
        text=text,
        chapter=None,
        section=None,
        article=None,
        paragraph=None,
        page_start=1,
        page_end=1,
        token_count=len(text.split()),
        topics=[],
        legal_status="active",
        source_url="",
        embedding=embedding,
        metadata={},
    )


def run_retrieval_evaluation(
    dataset_path: Path,
    top_k: int = 5,
) -> dict:
    """Run retrieval-only evaluation on golden questions."""
    metadata, questions = load_evaluation_dataset(dataset_path)
    provider = HashEmbeddingProvider()

    # Collect all unique document IDs
    all_doc_ids = set()
    for q in questions:
        all_doc_ids.update(q.expected_document_ids)

    # Create synthetic documents
    documents = [_make_synthetic_document(doc_id, provider) for doc_id in sorted(all_doc_ids)]

    # Build retrieval engine
    engine = RetrievalEngine(documents=documents, top_k=max(top_k, len(documents)))

    # Evaluate per question
    results = []
    for question in questions:
        retrieval = engine.search(question.question, top_k=max(top_k, len(documents)))
        retrieved_ids = list(dict.fromkeys(
            r.document.document_id for r in retrieval.results
        ))[:top_k]

        if question.should_refuse:
            results.append({
                "question_id": question.question_id,
                "category": question.category,
                "should_refuse": True,
                "refused": retrieval.should_refuse,
                "recall_at_k": None,
                "reciprocal_rank": None,
                "ndcg_at_k": None,
            })
        else:
            r5 = recall_at_k(question.expected_document_ids, retrieved_ids, 5)
            rr = reciprocal_rank(question.expected_document_ids, retrieved_ids)
            ndcg = ndcg_at_k(question.expected_document_ids, retrieved_ids, 10)
            results.append({
                "question_id": question.question_id,
                "category": question.category,
                "should_refuse": False,
                "refused": retrieval.should_refuse,
                "retrieved_ids": retrieved_ids,
                "expected_ids": question.expected_document_ids,
                "recall_at_k": r5,
                "reciprocal_rank": rr,
                "ndcg_at_k": ndcg,
            })

    # Aggregate metrics
    answerable = [r for r in results if not r["should_refuse"]]
    refusal = [r for r in results if r["should_refuse"]]

    recall_values = [r["recall_at_k"] for r in answerable if r["recall_at_k"] is not None]
    rr_values = [r["reciprocal_rank"] for r in answerable if r["reciprocal_rank"] is not None]
    ndcg_values = [r["ndcg_at_k"] for r in answerable if r["ndcg_at_k"] is not None]

    # Per-category breakdown
    categories = {}
    for q in questions:
        cat = q.category
        if cat not in categories:
            categories[cat] = {"total": 0, "answerable": 0, "refusal": 0, "recalls": [], "rrs": []}
        categories[cat]["total"] += 1
        if q.should_refuse:
            categories[cat]["refusal"] += 1
        else:
            categories[cat]["answerable"] += 1

    for r in results:
        cat = r["category"]
        if not r["should_refuse"] and r["recall_at_k"] is not None:
            categories[cat]["recalls"].append(r["recall_at_k"])
            categories[cat]["rrs"].append(r["reciprocal_rank"])

    report = {
        "dataset": str(dataset_path),
        "question_count": len(questions),
        "answerable_count": len(answerable),
        "refusal_count": len(refusal),
        "top_k": top_k,
        "overall": {
            "recall_at_k": round(mean(recall_values), 4) if recall_values else 0.0,
            "mean_reciprocal_rank": round(mean(rr_values), 4) if rr_values else 0.0,
            "ndcg_at_10": round(mean(ndcg_values), 4) if ndcg_values else 0.0,
        },
        "per_category": {
            cat: {
                "total": info["total"],
                "answerable": info["answerable"],
                "refusal": info["refusal"],
                "recall_at_k": round(mean(info["recalls"]), 4) if info["recalls"] else None,
                "mean_reciprocal_rank": round(mean(info["rrs"]), 4) if info["rrs"] else None,
            }
            for cat, info in sorted(categories.items())
        },
        "questions": results,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrieval metrics on golden questions.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parent / "golden_questions.json",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = run_retrieval_evaluation(args.dataset, args.top_k)

    output_path = args.output or args.dataset.parent / "retrieval_metrics_report.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Print summary
    print(f"Dataset: {report['question_count']} questions ({report['answerable_count']} answerable, {report['refusal_count']} refusal)")
    print(f"Top-K: {report['top_k']}")
    print(f"Overall Recall@{report['top_k']}: {report['overall']['recall_at_k']:.2%}")
    print(f"Overall MRR: {report['overall']['mean_reciprocal_rank']:.4f}")
    print(f"Overall nDCG@10: {report['overall']['ndcg_at_10']:.4f}")
    print()
    print("Per-category breakdown:")
    for cat, info in report["per_category"].items():
        r = info["recall_at_k"]
        rr = info["mean_reciprocal_rank"]
        r_str = f"{r:.2%}" if r is not None else "N/A"
        rr_str = f"{rr:.4f}" if rr is not None else "N/A"
        print(f"  {cat:25s}  recall={r_str:6s}  mrr={rr_str}  ({info['answerable']} answered)")
    print(f"\nReport written to {output_path}")


if __name__ == "__main__":
    main()
