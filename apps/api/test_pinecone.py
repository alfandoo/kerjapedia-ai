"""Quick Pinecone connection test."""

import os
import sys
from pathlib import Path

# Add apps/api to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

# Load .env using absolute path
env_path = Path("F:/Alfando/Portofolio/KerjaPediaAI/.env")
if env_path.exists():
    load_dotenv(env_path, override=True)
    print(f"Loaded .env from {env_path}")
else:
    print(f"ERROR: .env not found at {env_path}")
    sys.exit(1)

# Check API key
api_key = os.getenv("PINECONE_API_KEY")
if not api_key:
    print("ERROR: PINECONE_API_KEY not found in environment")
    sys.exit(1)
print(f"API key found: {api_key[:20]}...")

from app.services.ingestion.embeddings import BGEM3EmbeddingProvider
from app.services.retrieval.pinecone_store import PineconeConfig, PineconeRetrievalStore

# Create provider
print("Loading BGE-M3 model...")
provider = BGEM3EmbeddingProvider()
print(f"Model loaded. Dimension: {provider.dimensions}")

# Create store
config = PineconeConfig(
    api_key=api_key,
    index_name=os.getenv("PINECONE_INDEX_NAME", "kerjapedia-regulations-v2"),
    namespace=os.getenv("PINECONE_NAMESPACE", "production"),
    cloud=os.getenv("PINECONE_CLOUD", "aws"),
    region=os.getenv("PINECONE_REGION", "us-east-1"),
)

store = PineconeRetrievalStore(
    config=config,
    embedding_provider=provider,
)

# Test query
print("\nTesting query: 'Berapa kompensasi PKWT?'")
try:
    response = store.search("Berapa kompensasi PKWT?", top_k=3)
    print(f"Results: {len(response.results)}")
    print(f"Should refuse: {response.should_refuse}")
    for i, r in enumerate(response.results[:3]):
        print(f"  {i+1}. {r.document.document_id} (score: {r.final_score:.4f})")
        print(f"     {r.document.text[:100]}...")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

print("\nTest complete!")
