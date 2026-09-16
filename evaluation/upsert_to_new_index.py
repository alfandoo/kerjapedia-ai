"""Upsert embeddings from JSONL file to new Pinecone index.

Usage:
    python evaluation/upsert_to_new_index.py [--batch-size 100] [--namespace production] [--dry-run]
"""

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv("F:/Alfando/Portofolio/KerjaPediaAI/.env")

import os

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "kerjapedia")
NAMESPACE = os.getenv("PINECONE_NAMESPACE", "production")

EMBEDDINGS_FILE = Path(
    "F:/Alfando/Portofolio/KerjaPediaAI/storage/ingestion/embeddings/"
    "BAAI-bge-m3/5617a9f61b028005a4858fdac845db406aefb181/bge_m3_embeddings.jsonl"
)


def load_embeddings(path: Path):
    """Yield (vector_id, dense, sparse, metadata) from JSONL."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            vector_id = row["chunk_id"]
            dense = row["dense_vector"]
            sparse = row.get("sparse_vector", {})
            # Extract regulation type from chunk_id (e.g., PERMENAKER-1-2025-... -> permenaker)
            reg_type = vector_id.split("-")[0].lower() if "-" in vector_id else "unknown"
            metadata = {
                "content_hash": row.get("content_hash", ""),
                "model": row.get("model", ""),
                "vector_space": row.get("vector_space", ""),
                "legal_status": "active",
                "regulation_type": reg_type,
            }
            sparse_pinecone = {"indices": [int(k) for k in sparse.keys()], "values": [float(v) for v in sparse.values()]}
            yield vector_id, dense, sparse_pinecone, metadata


def upsert_batch(index, vectors, namespace):
    """Upsert a batch of vectors with retry on rate limit."""
    for attempt in range(3):
        try:
            index.upsert(vectors=vectors, namespace=namespace)
            return True
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                wait = 2 ** (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    return False


def main():
    parser = argparse.ArgumentParser(description="Upsert embeddings to new Pinecone index")
    parser.add_argument("--batch-size", type=int, default=100, help="Vectors per batch")
    parser.add_argument("--namespace", type=str, default=NAMESPACE, help="Pinecone namespace")
    parser.add_argument("--dry-run", action="store_true", help="Count without upserting")
    args = parser.parse_args()

    print(f"Pinecone API key: {PINECONE_API_KEY[:20]}...")
    print(f"Index: {INDEX_NAME}")
    print(f"Namespace: {args.namespace}")
    print(f"Embeddings file: {EMBEDDINGS_FILE}")
    print()

    pc = Pinecone(api_key=PINECONE_API_KEY)
    indexes = [idx.name for idx in pc.list_indexes()]
    print(f"Available indexes: {indexes}")

    if INDEX_NAME not in indexes:
        print(f"Creating index '{INDEX_NAME}'...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=1024,
            metric="cosine",
            spec={"serverless": {"cloud": "aws", "region": "us-east-1"}},
        )
        print("Waiting for index to be ready...")
        while True:
            desc = pc.describe_index(INDEX_NAME)
            if desc.status.get("ready"):
                break
            time.sleep(2)
        print("Index ready.")

    index = pc.Index(INDEX_NAME)
    stats = index.describe_index_stats()
    print(f"Index stats: {stats}")
    print()

    batch = []
    total = 0
    start_time = time.time()

    for vector_id, dense, sparse, metadata in load_embeddings(EMBEDDINGS_FILE):
        batch.append({
            "id": vector_id,
            "values": dense,
            "sparse_values": sparse,
            "metadata": metadata,
        })
        total += 1

        if len(batch) >= args.batch_size:
            if args.dry_run:
                print(f"  Would upsert batch of {len(batch)} (total so far: {total})")
            else:
                elapsed = time.time() - start_time
                rate = total / elapsed if elapsed > 0 else 0
                print(f"  Upserting batch (total: {total}, rate: {rate:.1f}/s)")
                upsert_batch(index, batch, args.namespace)
            batch = []

    if batch:
        if args.dry_run:
            print(f"  Final batch of {len(batch)} (total: {total})")
        else:
            upsert_batch(index, batch, args.namespace)

    elapsed = time.time() - start_time
    print(f"\nDone. Total vectors: {total}, Time: {elapsed:.1f}s")

    if not args.dry_run:
        stats = index.describe_index_stats()
        print(f"Final index stats: {stats}")


if __name__ == "__main__":
    main()
