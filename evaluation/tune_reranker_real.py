"""Real reranker evaluation using Pinecone production data.

Connects to Pinecone, embeds real queries using BGE-M3, and evaluates
different reranker configurations on actual retrieval results.

Usage:
    python evaluation/tune_reranker_real.py --dataset evaluation/golden_questions.json --top-k 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from app.core.config import settings
from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
from app.services.providers import embedding_provider_from_settings, pinecone_store_from_settings
from app.services.retrieval.pinecone_store import PineconeRetrievalStore
from app.services.retrieval.reranker import DEFAULT_RERANK_WEIGHTS, RerankWeights


# Configuration sweep — different reranker weight combinations
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

# Retry configuration for rate limits
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2.0
RATE_LIMIT_DELAY_SECONDS = 5.0


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if the error is a rate limit error."""
    return "429" in str(exc) or "rate limit" in str(exc).lower() or "egress limit" in str(exc).lower()


def _retry_with_backoff(func, *args, max_retries=MAX_RETRIES, **kwargs):
    """Execute function with retry logic for rate limits."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if _is_rate_limit_error(exc) and attempt < max_retries - 1:
                delay = RETRY_DELAY_SECONDS * (attempt + 1)
                print(f"    Rate limited, retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise


def run_real_evaluation(
    store: PineconeRetrievalStore,
    questions: list,
    top_k: int = 5,
    delay_between_queries: float = 0.0,
    skip_cross_encoder: bool = True,
    configs: list[str] | None = None,
) -> list[dict]:
    """Evaluate different reranker weights using real Pinecone data."""
    results = []

    sweep = WEIGHT_SWEEP if configs is None else [(n, w) for n, w in WEIGHT_SWEEP if n in configs]

    for name, weights in sweep:
        print(f"\nEvaluating: {name}...")
        print(f"  Weights: fusion={weights.fusion}, lexical={weights.lexical}, "
              f"semantic={weights.semantic}, overlap={weights.overlap}")

        recalls_5 = []
        recalls_10 = []
        precisions_5 = []
        ranks = []
        ndcgs = []
        hit_count = 0
        total_queries = 0
        latencies = []
        errors = 0
        rate_limit_hits = 0

        for question in questions:
            if question.should_refuse:
                continue

            try:
                # Time the full retrieval
                start_time = time.perf_counter()

                # Search Pinecone with custom rerank weights (with retry)
                retrieval = _retry_with_backoff(
                    store.search,
                    question.question,
                    top_k=top_k,
                    rerank_weights=weights,
                    skip_cross_encoder=skip_cross_encoder,
                )

                total_time = (time.perf_counter() - start_time) * 1000
                latencies.append(total_time)

                # Extract retrieved document IDs (chunk_id -> regulation ID)
                # chunk_id format: PP-35-2021-ab51a03238716cefb11d31c0
                # expected format: PP-35-2021
                def _extract_reg_id(chunk_id: str) -> str:
                    parts = chunk_id.split("-")
                    if len(parts) >= 3:
                        return "-".join(parts[:3])
                    return chunk_id

                retrieved_ids = list(dict.fromkeys(
                    _extract_reg_id(r.document.chunk_id or r.document.document_id)
                    for r in retrieval.results
                ))[:top_k]

                # Calculate metrics
                recalls_5.append(recall_at_k(question.expected_document_ids, retrieved_ids, 5))
                recalls_10.append(recall_at_k(question.expected_document_ids, retrieved_ids, 10))
                precisions_5.append(precision_at_k(question.expected_document_ids, retrieved_ids, 5))
                ranks.append(reciprocal_rank(question.expected_document_ids, retrieved_ids))
                ndcgs.append(ndcg_at_k(question.expected_document_ids, retrieved_ids, 10))

                if any(doc_id in question.expected_document_ids for doc_id in retrieved_ids):
                    hit_count += 1

                total_queries += 1

                # Rate limiting
                if delay_between_queries > 0:
                    time.sleep(delay_between_queries)

            except Exception as e:
                errors += 1
                if _is_rate_limit_error(e):
                    rate_limit_hits += 1
                    print(f"  Rate limit hit on {question.question_id}, waiting {RATE_LIMIT_DELAY_SECONDS}s...")
                    time.sleep(RATE_LIMIT_DELAY_SECONDS)
                else:
                    print(f"  Error on question {question.question_id}: {e}")
                continue

        # Calculate averages
        n = len(recalls_5)
        if n == 0:
            print(f"  No successful queries for {name}")
            continue

        avg_latency = sum(latencies) / n
        p95_latency = sorted(latencies)[int(n * 0.95)] if n >= 2 else latencies[0]

        results.append({
            "name": name,
            "weights": asdict(weights),
            "evaluated": n,
            "errors": errors,
            "rate_limit_hits": rate_limit_hits,
            "recall_at_5": round(sum(recalls_5) / n, 4),
            "recall_at_10": round(sum(recalls_10) / n, 4),
            "precision_at_5": round(sum(precisions_5) / n, 4),
            "hit_rate": round(hit_count / n, 4),
            "mean_reciprocal_rank": round(sum(ranks) / n, 4),
            "ndcg_at_10": round(sum(ndcgs) / n, 4),
            "latency_ms": {
                "avg": round(avg_latency, 2),
                "p95": round(p95_latency, 2),
                "min": round(min(latencies), 2),
                "max": round(max(latencies), 2),
            },
        })

        print(f"  Results: Recall@5={results[-1]['recall_at_5']:.2%}, "
              f"MRR={results[-1]['mean_reciprocal_rank']:.4f}, "
              f"nDCG={results[-1]['ndcg_at_10']:.4f}")
        print(f"  Latency: avg={avg_latency:.1f}ms, p95={p95_latency:.1f}ms")
        print(f"  Queries: {total_queries} successful, {errors} errors, {rate_limit_hits} rate limits")

    # Sort by recall@5 then MRR
    results.sort(key=lambda r: (r["recall_at_5"], r["mean_reciprocal_rank"]), reverse=True)
    return results


def _generate_recommendation(results: list[dict]) -> str:
    """Generate recommendation based on results."""
    if not results:
        return "No results"

    best = results[0]
    baseline = next((r for r in results if r["name"] == "baseline"), None)

    if baseline and best["name"] != baseline:
        recall_improvement = best["recall_at_5"] - baseline["recall_at_5"]
        mrr_improvement = best["mean_reciprocal_rank"] - baseline["mean_reciprocal_rank"]
        return (
            f"Switch from baseline to {best['name']}: "
            f"+{recall_improvement:.1%} recall@5, +{mrr_improvement:.4f} MRR"
        )
    else:
        return "Current baseline weights are near-optimal"


def main() -> None:
    parser = argparse.ArgumentParser(description="Real reranker evaluation with Pinecone")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).parent / "golden_questions.json",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--namespace", type=str, default=None, help="Override Pinecone namespace")
    parser.add_argument("--delay", type=float, default=0.1, help="Delay between queries (seconds)")
    parser.add_argument("--skip-cross-encoder", action="store_true", default=True,
                        help="Skip cross-encoder reranking (default: True)")
    parser.add_argument("--use-cross-encoder", action="store_true", default=False,
                        help="Enable cross-encoder reranking")
    parser.add_argument("--configs", nargs="+", default=None,
                        help="Run only specific configs (e.g., --configs baseline balanced)")
    args = parser.parse_args()

    # Determine cross-encoder setting
    skip_cross_encoder = not args.use_cross_encoder

    # Load dataset
    metadata, questions = load_evaluation_dataset(args.dataset)
    answerable = [q for q in questions if not q.should_refuse]
    print(f"Loaded {len(questions)} questions ({len(answerable)} answerable)")

    # Initialize providers
    print("\nConnecting to Pinecone...")
    print(f"  Index: {settings.pinecone_index_name}")
    embedding_provider = embedding_provider_from_settings(settings)
    namespace = args.namespace or settings.pinecone_namespace
    print(f"  Namespace: {namespace}")
    print(f"  Cross-encoder: {'ENABLED' if not skip_cross_encoder else 'DISABLED (heuristic only)'}")

    store = pinecone_store_from_settings(settings, namespace=namespace)

    # Run evaluation
    print(f"\nRunning evaluation with top_k={args.top_k}...")
    results = run_real_evaluation(store, answerable, args.top_k, args.delay, skip_cross_encoder, configs=args.configs)

    # Build report
    report = {
        "dataset": str(args.dataset),
        "question_count": len(questions),
        "answerable_count": len(answerable),
        "top_k": args.top_k,
        "pinecone_config": {
            "index_name": settings.pinecone_index_name,
            "namespace": namespace,
            "cloud": settings.pinecone_cloud,
            "region": settings.pinecone_region,
            "embedding_model": settings.embedding_model,
            "reranker_model": settings.reranker_model,
        },
        "weight_sweep": results,
        "best_config": results[0]["name"] if results else None,
        "recommendation": _generate_recommendation(results),
    }

    # Save report
    output_path = args.dataset.parent / "reranker_tuning_real_report.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    # Print summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"\n{'Config':<20} {'Recall@5':>10} {'MRR':>10} {'nDCG@10':>10} {'Latency':>12}")
    print("-" * 70)
    for r in results:
        print(f"{r['name']:<20} {r['recall_at_5']:>10.2%} {r['mean_reciprocal_rank']:>10.4f} "
              f"{r['ndcg_at_10']:>10.4f} {r['latency_ms']['avg']:>10.1f}ms")

    print("\n" + "=" * 70)
    print(f"Best config: {report['best_config']}")
    print(f"Recommendation: {report['recommendation']}")
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    main()
