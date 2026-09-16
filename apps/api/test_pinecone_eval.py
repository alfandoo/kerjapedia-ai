"""Quick Pinecone evaluation - processes 10 questions at a time."""

import json
import os
import sys
from pathlib import Path

# Add apps/api to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

# Load .env
env_path = Path("F:/Alfando/Portofolio/KerjaPediaAI/.env")
if env_path.exists():
    load_dotenv(env_path, override=True)

from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.metrics import recall_at_k, reciprocal_rank
from app.services.ingestion.embeddings import BGEM3EmbeddingProvider
from app.services.retrieval.pinecone_store import PineconeConfig, PineconeRetrievalStore

# Create provider and store
print("Loading BGE-M3 model...")
provider = BGEM3EmbeddingProvider()
print("Model loaded.")

config = PineconeConfig(
    api_key=os.getenv("PINECONE_API_KEY"),
    index_name=os.getenv("PINECONE_INDEX_NAME", "kerjapedia-regulations-v2"),
    namespace=os.getenv("PINECONE_NAMESPACE", "production"),
    cloud=os.getenv("PINECONE_CLOUD", "aws"),
    region=os.getenv("PINECONE_REGION", "us-east-1"),
)

store = PineconeRetrievalStore(config=config, embedding_provider=provider)

# Load dataset
dataset_path = Path("F:/Alfando/Portofolio/KerjaPediaAI/evaluation/golden_questions.json")
metadata, questions = load_evaluation_dataset(dataset_path)
print(f"Loaded {len(questions)} questions")

# Process first 20 questions
results = []
for i, q in enumerate(questions[:20]):
    print(f"[{i+1}/20] {q.question_id}: {q.question[:50]}...", end=" ")
    try:
        response = store.search(q.question, top_k=5)
        retrieved = list(dict.fromkeys(r.document.document_id for r in response.results))[:5]

        if q.should_refuse:
            status = "REFUSED" if response.should_refuse else "NOT_REFUSED"
            print(f" => {status}")
        else:
            r5 = recall_at_k(q.expected_document_ids, retrieved, 5)
            rr = reciprocal_rank(q.expected_document_ids, retrieved)
            print(f" => R@5={r5:.2%} MRR={rr:.2f} | {retrieved[:3]}")

        results.append({
            "question_id": q.question_id,
            "category": q.category,
            "should_refuse": q.should_refuse,
            "refused": response.should_refuse,
            "retrieved": retrieved,
            "expected": q.expected_document_ids,
            "recall_at_5": r5 if not q.should_refuse else None,
            "mrr": rr if not q.should_refuse else None,
        })
    except Exception as e:
        print(f" => ERROR: {e}")
        results.append({"question_id": q.question_id, "error": str(e)})

# Save results
output = Path("F:/Alfando/Portofolio/KerjaPediaAI/evaluation/pinecone_quick_eval.json")
output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nResults saved to {output}")

# Summary
answerable = [r for r in results if not r.get("should_refuse") and r.get("recall_at_5") is not None]
if answerable:
    avg_recall = sum(r["recall_at_5"] for r in answerable) / len(answerable)
    avg_mrr = sum(r["mrr"] for r in answerable) / len(answerable)
    print(f"\nSummary ({len(answerable)} answerable):")
    print(f"  Avg Recall@5: {avg_recall:.2%}")
    print(f"  Avg MRR: {avg_mrr:.4f}")
