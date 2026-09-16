"""Debug cross-encoder behavior on a single query."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from dotenv import load_dotenv
load_dotenv("F:/Alfando/Portofolio/KerjaPediaAI/.env")

from app.core.config import settings
from app.services.providers import embedding_provider_from_settings, pinecone_store_from_settings
from app.services.retrieval.reranker import DEFAULT_RERANK_WEIGHTS, RerankWeights

# Test with one question
test_query = "Apa itu UMK?"

embedding_provider = embedding_provider_from_settings(settings)
store = pinecone_store_from_settings(settings, namespace="production")

print("=== HEURISTIC ONLY ===")
retrieval_h = store.search(
    test_query,
    top_k=5,
    rerank_weights=DEFAULT_RERANK_WEIGHTS,
    skip_cross_encoder=True,
)
for i, r in enumerate(retrieval_h.results):
    print(f"  {i+1}. [{r.final_score:.4f}] {r.document.document_id} | {r.document.text[:80]}...")
print(f"  Timing: {retrieval_h.timing}")

print("\n=== WITH CROSS-ENCODER ===")
retrieval_ce = store.search(
    test_query,
    top_k=5,
    rerank_weights=DEFAULT_RERANK_WEIGHTS,
    skip_cross_encoder=False,
)
for i, r in enumerate(retrieval_ce.results):
    print(f"  {i+1}. [{r.final_score:.4f}] rerank={r.rerank_score:.4f} | {r.document.document_id} | {r.document.text[:80]}...")
print(f"  Timing: {retrieval_ce.timing}")
print(f"  Warnings: {retrieval_ce.warnings}")
