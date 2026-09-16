"""Full Pinecone evaluation - processes all 130 questions."""

import json
import os
import sys
from pathlib import Path
from statistics import mean

# Add apps/api to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

# Load .env
env_path = Path("F:/Alfando/Portofolio/KerjaPediaAI/.env")
if env_path.exists():
    load_dotenv(env_path, override=True)

from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.metrics import ndcg_at_k, precision_at_k, hit_rate, recall_at_k, reciprocal_rank
from app.services.ingestion.embeddings import BGEM3EmbeddingProvider
from app.services.retrieval.pinecone_store import PineconeConfig, PineconeRetrievalStore

# Create provider and store
print("Loading BGE-M3 model...")
provider = BGEM3EmbeddingProvider()
print("Model loaded.")

config = PineconeConfig(
    api_key=os.getenv("PINECONE_API_KEY"),
    index_name=os.getenv("PINECONE_INDEX_NAME", "kerjapedia"),
    namespace=os.getenv("PINECONE_NAMESPACE", "production"),
    cloud=os.getenv("PINECONE_CLOUD", "aws"),
    region=os.getenv("PINECONE_REGION", "us-east-1"),
)

store = PineconeRetrievalStore(config=config, embedding_provider=provider)

# Load dataset
dataset_path = Path("F:/Alfando/Portofolio/KerjaPediaAI/evaluation/golden_questions.json")
metadata, questions = load_evaluation_dataset(dataset_path)
print(f"Loaded {len(questions)} questions")

# Process all questions
results = []
errors = []

for i, q in enumerate(questions):
    print(f"[{i+1}/{len(questions)}] {q.question_id}: {q.question[:50]}...", end=" ")
    try:
        response = store.search(q.question, top_k=5)
        retrieved = list(dict.fromkeys(r.document.document_id for r in response.results))[:5]

        if q.should_refuse:
            status = "REFUSED" if response.should_refuse else "NOT_REFUSED"
            print(f" => {status}")
            results.append({
                "question_id": q.question_id,
                "category": q.category,
                "should_refuse": True,
                "refused": response.should_refuse,
                "retrieved": retrieved,
                "expected": q.expected_document_ids,
                "recall_at_5": None,
                "precision_at_5": None,
                "hit_rate": None,
                "mrr": None,
                "ndcg": None,
            })
        else:
            r5 = recall_at_k(q.expected_document_ids, retrieved, 5)
            p5 = precision_at_k(q.expected_document_ids, retrieved, 5)
            hr = hit_rate(q.expected_document_ids, retrieved, 5)
            rr = reciprocal_rank(q.expected_document_ids, retrieved)
            ndcg = ndcg_at_k(q.expected_document_ids, retrieved, 10)
            print(f" => R@5={r5:.2%} P@5={p5:.2%} HR={hr:.0f} MRR={rr:.2f} nDCG={ndcg:.2f}")
            results.append({
                "question_id": q.question_id,
                "category": q.category,
                "should_refuse": False,
                "refused": response.should_refuse,
                "retrieved": retrieved,
                "expected": q.expected_document_ids,
                "recall_at_5": r5,
                "precision_at_5": p5,
                "hit_rate": hr,
                "mrr": rr,
                "ndcg": ndcg,
            })
    except Exception as e:
        print(f" => ERROR: {e}")
        errors.append({"question_id": q.question_id, "error": str(e)})
        results.append({"question_id": q.question_id, "error": str(e)})

# Calculate aggregates
answerable = [r for r in results if not r.get("should_refuse") and r.get("recall_at_5") is not None]
refusal = [r for r in results if r.get("should_refuse")]
error_list = [r for r in results if r.get("error") is not None]

# Per-category breakdown
categories = {}
for q in questions:
    cat = q.category
    if cat not in categories:
        categories[cat] = {"total": 0, "answerable": 0, "refusal": 0, "errors": 0, "recalls": [], "precisions": [], "hits": [], "rrs": [], "ndcgs": []}
    categories[cat]["total"] += 1
    if q.should_refuse:
        categories[cat]["refusal"] += 1

for r in results:
    cat = r.get("category")
    if cat and cat in categories:
        if r.get("error"):
            categories[cat]["errors"] += 1
        elif not r.get("should_refuse"):
            if r.get("recall_at_5") is not None:
                categories[cat]["recalls"].append(r["recall_at_5"])
            if r.get("precision_at_5") is not None:
                categories[cat]["precisions"].append(r["precision_at_5"])
            if r.get("hit_rate") is not None:
                categories[cat]["hits"].append(r["hit_rate"])
            if r.get("mrr") is not None:
                categories[cat]["rrs"].append(r["mrr"])
            if r.get("ndcg") is not None:
                categories[cat]["ndcgs"].append(r["ndcg"])

# Build report
report = {
    "dataset": str(dataset_path),
    "question_count": len(questions),
    "answerable_count": len(answerable),
    "refusal_count": len(refusal),
    "error_count": len(error_list),
    "top_k": 5,
    "pinecone_config": {
        "index_name": os.getenv("PINECONE_INDEX_NAME"),
        "namespace": os.getenv("PINECONE_NAMESPACE"),
        "cloud": os.getenv("PINECONE_CLOUD"),
        "region": os.getenv("PINECONE_REGION"),
    },
    "overall": {
        "recall_at_5": round(mean([r["recall_at_5"] for r in answerable]), 4) if answerable else 0.0,
        "precision_at_5": round(mean([r["precision_at_5"] for r in answerable]), 4) if answerable else 0.0,
        "hit_rate": round(mean([r["hit_rate"] for r in answerable]), 4) if answerable else 0.0,
        "mean_reciprocal_rank": round(mean([r["mrr"] for r in answerable]), 4) if answerable else 0.0,
        "ndcg_at_10": round(mean([r["ndcg"] for r in answerable]), 4) if answerable else 0.0,
    },
    "per_category": {
        cat: {
            "total": info["total"],
            "answerable": info["answerable"],
            "refusal": info["refusal"],
            "errors": info["errors"],
            "recall_at_5": round(mean(info["recalls"]), 4) if info["recalls"] else None,
            "precision_at_5": round(mean(info["precisions"]), 4) if info["precisions"] else None,
            "hit_rate": round(mean(info["hits"]), 4) if info["hits"] else None,
            "mean_reciprocal_rank": round(mean(info["rrs"]), 4) if info["rrs"] else None,
            "ndcg_at_10": round(mean(info["ndcgs"]), 4) if info["ndcgs"] else None,
        }
        for cat, info in sorted(categories.items())
    },
    "questions": results,
}

# Save report
output = Path("F:/Alfando/Portofolio/KerjaPediaAI/evaluation/pinecone_full_eval.json")
output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

# Print summary
print("\n" + "="*60)
print("FULL EVALUATION COMPLETE")
print("="*60)
print(f"Dataset: {report['question_count']} questions ({report['answerable_count']} answerable, {report['refusal_count']} refusal)")
if report['error_count'] > 0:
    print(f"Errors: {report['error_count']}")
print(f"Top-K: {report['top_k']}")
print(f"Pinecone: {report['pinecone_config']['index_name']} / {report['pinecone_config']['namespace']}")
print()
print("=== Overall Metrics ===")
o = report["overall"]
print(f"  Recall@5:          {o['recall_at_5']:.2%}")
print(f"  Precision@5:       {o['precision_at_5']:.2%}")
print(f"  Hit Rate:          {o['hit_rate']:.2%}")
print(f"  MRR:              {o['mean_reciprocal_rank']:.4f}")
print(f"  nDCG@10:          {o['ndcg_at_10']:.4f}")
print()
print("=== Per-Category Breakdown ===")
for cat, info in report["per_category"].items():
    r = info["recall_at_5"]
    p = info["precision_at_5"]
    hr = info["hit_rate"]
    rr = info["mean_reciprocal_rank"]
    ndcg = info["ndcg_at_10"]
    r_str = f"{r:.2%}" if r is not None else "N/A"
    p_str = f"{p:.2%}" if p is not None else "N/A"
    hr_str = f"{hr:.2%}" if hr is not None else "N/A"
    rr_str = f"{rr:.4f}" if rr is not None else "N/A"
    ndcg_str = f"{ndcg:.4f}" if ndcg is not None else "N/A"
    err_str = f" [{info['errors']} errors]" if info['errors'] > 0 else ""
    print(f"  {cat:25s}  R@5={r_str:6s}  P@5={p_str:6s}  HR={hr_str:6s}  MRR={rr_str}{err_str}")
print(f"\nReport saved to {output}")
