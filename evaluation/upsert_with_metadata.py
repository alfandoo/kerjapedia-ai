"""Upsert embeddings with full metadata from preembedding artifacts.

Usage:
    python evaluation/upsert_with_metadata.py [--batch-size 100] [--namespace production] [--dry-run]
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

PREEMBEDDING_DIR = Path("F:/Alfando/Portofolio/KerjaPediaAI/storage/ingestion/preembedding/artifacts")


def load_chunks_metadata(preembedding_dir: Path) -> dict[str, dict]:
    """Load all chunk metadata from preembedding artifacts."""
    metadata_map = {}
    for doc_dir in preembedding_dir.iterdir():
        if not doc_dir.is_dir():
            continue
        for chunk_dir in doc_dir.iterdir():
            if not chunk_dir.is_dir():
                continue
            chunks_file = chunk_dir / "chunks.json"
            if not chunks_file.exists():
                continue
            with open(chunks_file, "r", encoding="utf-8") as f:
                chunks = json.load(f)
                for chunk in chunks:
                    chunk_id = chunk.get("chunk_id", "")
                    if chunk_id:
                        # Extract metadata for Pinecone
                        doc_meta = chunk.get("metadata", {}).get("document", {})
                        struct_meta = chunk.get("metadata", {}).get("structure", {})
                        pasal = struct_meta.get("pasal") or ""
                        ayat = struct_meta.get("ayat") or ""
                        meta = {
                            "document_id": chunk.get("document_id", ""),
                            "text": chunk.get("content", "")[:1000],  # Truncate for metadata
                            "legal_status": doc_meta.get("regulation_status", "active"),
                            "regulation_type": doc_meta.get("document_type", "").lower(),
                            "year": doc_meta.get("year", 0),
                            "document_title": doc_meta.get("document_title", ""),
                            "source_url": doc_meta.get("source_url", ""),
                            "pasal": pasal,
                            "bab": struct_meta.get("bab") or "",
                            # API-reader governance fields: curated corpus is
                            # verified/published per dataset/metadata.json.
                            "verification_status": "verified",
                            "legal_review_status": "verified",
                            "source_verification_status": "verified",
                            "publication_status": "published",
                            "is_current": True,
                            # API-reader citation fields (normalized to API format).
                            "chapter": struct_meta.get("bab") or "",
                            "section": struct_meta.get("bagian") or "",
                            "article": (
                                pasal
                                if not pasal or pasal.strip().lower().startswith("pasal")
                                else f"Pasal {pasal.strip()}"
                            ),
                            "paragraph": (
                                ayat
                                if not ayat or "ayat" in ayat.strip().lower()
                                else f"Ayat ({ayat.strip()})"
                            ),
                            "page_start": struct_meta.get("page_start") or 0,
                            "page_end": struct_meta.get("page_end") or 0,
                            "token_count": chunk.get("token_count") or 0,
                        }
                        metadata_map[chunk_id] = meta
    return metadata_map


def load_embeddings(path: Path, metadata_map: dict[str, dict]):
    """Yield (vector_id, dense, sparse, metadata) from JSONL with chunk metadata."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            vector_id = row["chunk_id"]
            dense = row["dense_vector"]
            sparse = row.get("sparse_vector", {})

            # Get metadata from preembedding artifacts
            chunk_meta = metadata_map.get(vector_id, {})

            # Merge metadata — Pinecone only accepts str, number, bool, list[str]
            metadata = {
                "document_id": chunk_meta.get("document_id") or "",
                "text": (chunk_meta.get("text") or "")[:1000],
                "legal_status": chunk_meta.get("legal_status") or "active",
                "regulation_type": chunk_meta.get("regulation_type") or "",
                "year": chunk_meta.get("year") or 0,
                "document_title": chunk_meta.get("document_title") or "",
                "source_url": chunk_meta.get("source_url") or "",
                "pasal": chunk_meta.get("pasal") or "",
                "bab": chunk_meta.get("bab") or "",
                "content_hash": row.get("content_hash") or "",
                "model": row.get("model") or "",
                "vector_space": row.get("vector_space") or "",
                "verification_status": chunk_meta.get("verification_status") or "verified",
                "legal_review_status": chunk_meta.get("legal_review_status") or "verified",
                "source_verification_status": (
                    chunk_meta.get("source_verification_status") or "verified"
                ),
                "publication_status": chunk_meta.get("publication_status") or "published",
                "is_current": True,
                "chapter": chunk_meta.get("chapter") or "",
                "section": chunk_meta.get("section") or "",
                "article": chunk_meta.get("article") or "",
                "paragraph": chunk_meta.get("paragraph") or "",
                "page_start": chunk_meta.get("page_start") or 0,
                "page_end": chunk_meta.get("page_end") or 0,
                "token_count": chunk_meta.get("token_count") or 0,
            }

            sparse_pinecone = {
                "indices": [int(k) for k in sparse.keys()],
                "values": [float(v) for v in sparse.values()],
            }
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
    parser = argparse.ArgumentParser(description="Upsert embeddings with metadata")
    parser.add_argument("--batch-size", type=int, default=100, help="Vectors per batch")
    parser.add_argument("--namespace", type=str, default=NAMESPACE, help="Pinecone namespace")
    parser.add_argument("--dry-run", action="store_true", help="Count without upserting")
    args = parser.parse_args()

    print(f"Pinecone API key: {PINECONE_API_KEY[:20]}...")
    print(f"Index: {INDEX_NAME}")
    print(f"Namespace: {args.namespace}")
    print(f"Embeddings file: {EMBEDDINGS_FILE}")
    print(f"Preembedding dir: {PREEMBEDDING_DIR}")
    print()

    # Load chunk metadata
    print("Loading chunk metadata from preembedding artifacts...")
    metadata_map = load_chunks_metadata(PREEMBEDDING_DIR)
    print(f"Loaded metadata for {len(metadata_map)} chunks")
    print()

    pc = Pinecone(api_key=PINECONE_API_KEY)
    indexes = [idx.name for idx in pc.list_indexes()]
    print(f"Available indexes: {indexes}")

    if INDEX_NAME not in indexes:
        print(f"Creating index '{INDEX_NAME}'...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=1024,
            metric="dotproduct",
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
    matched = 0
    start_time = time.time()

    for vector_id, dense, sparse, metadata in load_embeddings(EMBEDDINGS_FILE, metadata_map):
        batch.append({
            "id": vector_id,
            "values": dense,
            "sparse_values": sparse,
            "metadata": metadata,
        })
        total += 1
        if metadata.get("document_id"):
            matched += 1

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
    print(f"\nDone. Total vectors: {total}, Matched: {matched}, Time: {elapsed:.1f}s")

    if not args.dry_run:
        stats = index.describe_index_stats()
        print(f"Final index stats: {stats}")


if __name__ == "__main__":
    main()
