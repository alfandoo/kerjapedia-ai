"""Real Pinecone evaluation harness.

Connects to the actual Pinecone store and runs retrieval evaluation
on golden questions using real ingestion data.

Usage:
    cd apps/api
    python -m evaluation.pinecone_eval --top-k 5 --output pinecone_eval_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add apps/api to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

# Load .env using absolute path
env_path = Path("F:/Alfando/Portofolio/KerjaPediaAI/.env")
if env_path.exists():
    load_dotenv(env_path, override=True)
    print(f"Loaded .env from {env_path}")
else:
    print(f"Warning: .env not found at {env_path}")

from app.core.config import Settings
from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.metrics import ndcg_at_k, recall_at_k, reciprocal_rank
from app.services.ingestion.embeddings import EmbeddingProvider, embed_queries_hybrid
from app.services.retrieval.pinecone_store import PineconeConfig, PineconeRetrievalStore


def create_embedding_provider() -> EmbeddingProvider:
    """Create the appropriate embedding provider based on settings."""
    provider_name = os.getenv("EMBEDDING_PROVIDER", "hash")
    model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

    if provider_name == "bge_m3":
        try:
            from app.services.ingestion.embeddings import BGEM3EmbeddingProvider
            return BGEM3EmbeddingProvider(model_name=model_name)
        except Exception as e:
            print(f"Warning: Could not load BGE-M3 provider: {e}")
            print("Falling back to hash embedding provider")

    from app.services.ingestion.embeddings import HashEmbeddingProvider
    return HashEmbeddingProvider()


def create_pinecone_store() -> PineconeRetrievalStore:
    """Create a PineconeRetrievalStore from environment variables."""
    settings = Settings()

    # Get Pinecone config from environment
    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME", "kerjapedia-regulations-v2")
    namespace = os.getenv("PINECONE_NAMESPACE", "production")
    cloud = os.getenv("PINECONE_CLOUD", "aws")
    region = os.getenv("PINECONE_REGION", "us-east-1")

    if not api_key:
        raise RuntimeError(
            "PINECONE_API_KEY is required. Set it in .env or environment."
        )

    config = PineconeConfig(
        api_key=api_key,
        index_name=index_name,
        namespace=namespace,
        cloud=cloud,
        region=region,
        dimension=int(os.getenv("EMBEDDING_DIMENSION", "1024")),
    )

    embedding_provider = create_embedding_provider()

    store = PineconeRetrievalStore(
        config=config,
        embedding_provider=embedding_provider,
        reranker_provider=settings.reranker_provider,
        reranker_model=settings.reranker_model,
        fail_closed=settings.rag_fail_closed,
        diversity_lambda=settings.retrieval_diversity_lambda,
        hybrid_alpha=settings.retrieval_hybrid_alpha,
        allow_unpublished=settings.rag_allow_unpublished,
    )

    return store


def run_pinecone_evaluation(
    dataset_path: Path,
    top_k: int = 5,
) -> dict:
    """Run evaluation using real Pinecone store."""
    metadata, questions = load_evaluation_dataset(dataset_path)

    print(f"Connecting to Pinecone...")
    store = create_pinecone_store()

    # Check if store is ready
    if not store.is_ready():
        print("Warning: Pinecone store is not ready. Connection may fail.")

    print(f"Running evaluation on {len(questions)} questions...")

    results = []
    for i, question in enumerate(questions):
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i + 1}/{len(questions)}")

        try:
            # Retrieve from Pinecone
            retrieval = store.search(
                question.question,
                top_k=top_k,
                context_topics=tuple(question.expected_topics[:2]) if question.expected_topics else (),
                context_document_ids=tuple(question.expected_document_ids[:1]) if question.expected_document_ids else (),
            )

            # Extract retrieved document IDs
            retrieved_ids = list(dict.fromkeys(
                r.document.document_id for r in retrieval.results
            ))[:top_k]

            if question.should_refuse:
                results.append({
                    "question_id": question.question_id,
                    "category": question.category,
                    "should_refuse": True,
                    "refused": retrieval.should_refuse,
                    "refusal_reason": retrieval.refusal_reason,
                    "result_count": len(retrieval.results),
                    "warnings": retrieval.warnings,
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
                    "result_count": len(retrieval.results),
                    "warnings": retrieval.warnings,
                    "recall_at_k": r5,
                    "reciprocal_rank": rr,
                    "ndcg_at_k": ndcg,
                })
        except Exception as e:
            results.append({
                "question_id": question.question_id,
                "category": question.category,
                "should_refuse": question.should_refuse,
                "error": str(e),
                "recall_at_k": None,
                "reciprocal_rank": None,
                "ndcg_at_k": None,
            })

    # Aggregate metrics
    answerable = [r for r in results if not r.get("should_refuse") and r.get("error") is None]
    refusal = [r for r in results if r.get("should_refuse")]
    errors = [r for r in results if r.get("error") is not None]

    recall_values = [r["recall_at_k"] for r in answerable if r["recall_at_k"] is not None]
    rr_values = [r["reciprocal_rank"] for r in answerable if r["reciprocal_rank"] is not None]
    ndcg_values = [r["ndcg_at_k"] for r in answerable if r["ndcg_at_k"] is not None]

    # Per-category breakdown
    categories = {}
    for q in questions:
        cat = q.category
        if cat not in categories:
            categories[cat] = {
                "total": 0, "answerable": 0, "refusal": 0, "errors": 0,
                "recalls": [], "rrs": [], "ndcgs": []
            }
        categories[cat]["total"] += 1
        if q.should_refuse:
            categories[cat]["refusal"] += 1

    for r in results:
        cat = r.get("category")
        if cat and cat in categories:
            if r.get("error"):
                categories[cat]["errors"] += 1
            elif not r.get("should_refuse"):
                if r["recall_at_k"] is not None:
                    categories[cat]["recalls"].append(r["recall_at_k"])
                if r["reciprocal_rank"] is not None:
                    categories[cat]["rrs"].append(r["reciprocal_rank"])
                if r["ndcg_at_k"] is not None:
                    categories[cat]["ndcgs"].append(r["ndcg_at_k"])

    from statistics import mean

    report = {
        "dataset": str(dataset_path),
        "question_count": len(questions),
        "answerable_count": len(answerable),
        "refusal_count": len(refusal),
        "error_count": len(errors),
        "top_k": top_k,
        "pinecone_config": {
            "index_name": os.getenv("PINECONE_INDEX_NAME"),
            "namespace": os.getenv("PINECONE_NAMESPACE"),
            "cloud": os.getenv("PINECONE_CLOUD"),
            "region": os.getenv("PINECONE_REGION"),
        },
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
                "errors": info["errors"],
                "recall_at_k": round(mean(info["recalls"]), 4) if info["recalls"] else None,
                "mean_reciprocal_rank": round(mean(info["rrs"]), 4) if info["rrs"] else None,
                "ndcg_at_10": round(mean(info["ndcgs"]), 4) if info["ndcgs"] else None,
            }
            for cat, info in sorted(categories.items())
        },
        "questions": results,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evaluation using real Pinecone store.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent.parent / "evaluation" / "golden_questions.json",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = run_pinecone_evaluation(args.dataset, args.top_k)

    output_path = args.output or args.dataset.parent / "pinecone_eval_report.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Print summary
    print(f"\nDataset: {report['question_count']} questions ({report['answerable_count']} answerable, {report['refusal_count']} refusal)")
    if report['error_count'] > 0:
        print(f"Errors: {report['error_count']}")
    print(f"Top-K: {report['top_k']}")
    print(f"Pinecone: {report['pinecone_config']['index_name']} / {report['pinecone_config']['namespace']}")
    print()
    print("=== Overall Metrics ===")
    o = report["overall"]
    print(f"  Recall@{report['top_k']}:          {o['recall_at_k']:.2%}")
    print(f"  MRR:              {o['mean_reciprocal_rank']:.4f}")
    print(f"  nDCG@10:          {o['ndcg_at_10']:.4f}")
    print()
    print("=== Per-Category Breakdown ===")
    for cat, info in report["per_category"].items():
        r = info["recall_at_k"]
        rr = info["mean_reciprocal_rank"]
        r_str = f"{r:.2%}" if r is not None else "N/A"
        rr_str = f"{rr:.4f}" if rr is not None else "N/A"
        err_str = f" [{info['errors']} errors]" if info['errors'] > 0 else ""
        print(f"  {cat:25s}  R@5={r_str:6s}  MRR={rr_str}{err_str}")
    print(f"\nReport written to {output_path}")


if __name__ == "__main__":
    main()
