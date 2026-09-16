"""Reranker weight and diversity lambda tuning sweep.

Tests different reranker weight configurations and MMR diversity parameters
on the golden questions dataset to find optimal settings.

Usage:
    python evaluation/tune_reranker.py --dataset evaluation/golden_questions.json --top-k 5
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

# Add apps/api to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.metrics import ndcg_at_k, recall_at_k, reciprocal_rank
from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.reranker import DEFAULT_RERANK_WEIGHTS, RerankWeights
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


# Extended weight sweep configurations
WEIGHT_SWEEP: list[tuple[str, RerankWeights]] = [
    ("baseline", DEFAULT_RERANK_WEIGHTS),
    ("semantic_heavy", RerankWeights(fusion=0.35, lexical=0.15, semantic=0.35, overlap=0.15)),
    ("lexical_heavy", RerankWeights(fusion=0.35, lexical=0.35, semantic=0.15, overlap=0.15)),
    ("fusion_heavy", RerankWeights(fusion=0.60, lexical=0.15, semantic=0.15, overlap=0.10)),
    ("overlap_heavy", RerankWeights(fusion=0.35, lexical=0.20, semantic=0.20, overlap=0.25)),
    ("balanced", RerankWeights(fusion=0.30, lexical=0.25, semantic=0.25, overlap=0.20)),
    ("topic_boosted", RerankWeights(fusion=0.40, lexical=0.20, semantic=0.20, overlap=0.15, topic_boost=0.40)),
    ("article_boosted", RerankWeights(fusion=0.40, lexical=0.20, semantic=0.20, overlap=0.15, article_boost=0.40)),
]

# MMR diversity lambda sweep
LAMBDA_SWEEP: list[float] = [0.3, 0.5, 0.7, 0.9]


def run_weight_sweep(
    questions: list,
    documents: list[RetrievalDocument],
    top_k: int = 5,
) -> list[dict]:
    """Test different reranker weight configurations."""
    rows = []
    for name, weights in WEIGHT_SWEEP:
        engine = RetrievalEngine(
            documents=documents,
            top_k=max(top_k, len(documents)),
            rerank_weights=weights,
        )
        recalls_5 = []
        recalls_10 = []
        ranks = []
        ndcgs = []
        for question in questions:
            if question.should_refuse:
                continue
            retrieval = engine.search(question.question, top_k=max(top_k, len(documents)))
            retrieved_ids = list(dict.fromkeys(
                r.document.document_id for r in retrieval.results
            ))[:top_k]
            recalls_5.append(recall_at_k(question.expected_document_ids, retrieved_ids, 5))
            recalls_10.append(recall_at_k(question.expected_document_ids, retrieved_ids, 10))
            ranks.append(reciprocal_rank(question.expected_document_ids, retrieved_ids))
            ndcgs.append(ndcg_at_k(question.expected_document_ids, retrieved_ids, 10))
        rows.append({
            "name": name,
            "weights": asdict(weights),
            "evaluated": len(recalls_5),
            "recall_at_5": round(sum(recalls_5) / len(recalls_5), 4) if recalls_5 else 0.0,
            "recall_at_10": round(sum(recalls_10) / len(recalls_10), 4) if recalls_10 else 0.0,
            "mean_reciprocal_rank": round(sum(ranks) / len(ranks), 4) if ranks else 0.0,
            "ndcg_at_10": round(sum(ndcgs) / len(ndcgs), 4) if ndcgs else 0.0,
        })
    rows.sort(key=lambda r: (r["recall_at_5"], r["mean_reciprocal_rank"]), reverse=True)
    return rows


def run_lambda_sweep(
    questions: list,
    documents: list[RetrievalDocument],
    top_k: int = 5,
) -> list[dict]:
    """Test different MMR diversity lambda values."""
    rows = []
    for lambda_param in LAMBDA_SWEEP:
        engine = RetrievalEngine(
            documents=documents,
            top_k=max(top_k, len(documents)),
            diversity_lambda=lambda_param,
        )
        recalls = []
        ranks = []
        for question in questions:
            if question.should_refuse:
                continue
            retrieval = engine.search(question.question, top_k=max(top_k, len(documents)))
            retrieved_ids = list(dict.fromkeys(
                r.document.document_id for r in retrieval.results
            ))[:top_k]
            recalls.append(recall_at_k(question.expected_document_ids, retrieved_ids, top_k))
            ranks.append(reciprocal_rank(question.expected_document_ids, retrieved_ids))
        rows.append({
            "diversity_lambda": lambda_param,
            "evaluated": len(recalls),
            "recall_at_k": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
            "mean_reciprocal_rank": round(sum(ranks) / len(ranks), 4) if ranks else 0.0,
        })
    rows.sort(key=lambda r: (r["recall_at_k"], r["mean_reciprocal_rank"]), reverse=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune reranker weights and diversity lambda.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parent / "golden_questions.json",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    metadata, questions = load_evaluation_dataset(args.dataset)
    provider = HashEmbeddingProvider()

    # Collect all unique document IDs
    all_doc_ids = set()
    for q in questions:
        all_doc_ids.update(q.expected_document_ids)

    # Create synthetic documents
    documents = [_make_synthetic_document(doc_id, provider) for doc_id in sorted(all_doc_ids)]

    # Run sweeps
    weight_results = run_weight_sweep(questions, documents, args.top_k)
    lambda_results = run_lambda_sweep(questions, documents, args.top_k)

    report = {
        "dataset": str(args.dataset),
        "question_count": len(questions),
        "top_k": args.top_k,
        "weight_sweep": weight_results,
        "lambda_sweep": lambda_results,
        "best_weight_config": weight_results[0]["name"] if weight_results else None,
        "best_lambda": lambda_results[0]["diversity_lambda"] if lambda_results else None,
    }

    output_path = args.output or args.dataset.parent / "reranker_tuning_report.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Print summary
    print(f"Dataset: {len(questions)} questions")
    print(f"Top-K: {args.top_k}")
    print()
    print("=== Weight Sweep Results ===")
    for row in weight_results:
        print(f"  {row['name']:20s}  R@5={row['recall_at_5']:.2%}  R@10={row['recall_at_10']:.2%}  MRR={row['mean_reciprocal_rank']:.4f}  nDCG={row['ndcg_at_10']:.4f}")
    print()
    print("=== Lambda Sweep Results ===")
    for row in lambda_results:
        print(f"  lambda={row['diversity_lambda']:.1f}  R@{args.top_k}={row['recall_at_k']:.2%}  MRR={row['mean_reciprocal_rank']:.4f}")
    print()
    print(f"Best weight config: {report['best_weight_config']}")
    print(f"Best lambda: {report['best_lambda']}")
    print(f"\nReport written to {output_path}")


if __name__ == "__main__":
    main()
