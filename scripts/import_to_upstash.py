"""DEPRECATED: import pre-computed BGE-M3 embeddings into Upstash Vector.

This script is preserved for rollback and baseline comparison only. It
upserts manually computed dense vectors, which is NOT the active pipeline.

Active pipeline: ``python scripts/index_upstash.py`` sends raw chunk text
to Upstash, which embeds server-side (``open-ai/text-embedding-3-small`` +
BM25 on a HYBRID index). See README "Upstash Vector Setup".

Usage:
    python scripts/import_to_upstash.py
    python scripts/import_to_upstash.py --dry-run
"""
import argparse
import json
import math
import os
import time
import warnings

warnings.warn(
    "scripts/import_to_upstash.py is deprecated; use scripts/index_upstash.py "
    "(hosted embeddings) for the active pipeline.",
    DeprecationWarning,
    stacklevel=2,
)

EMBEDDINGS_PATH = "storage/ingestion/embeddings/BAAI-bge-m3/5617a9f61b028005a4858fdac845db406aefb181/bge_m3_embeddings.jsonl"
CHUNKS_PATH = "storage/ingestion/preembedding/exports/chunks.jsonl"
# Credentials must come from the environment; never hardcode tokens.
UPSTASH_URL = os.environ.get("UPSTASH_VECTOR_URL", "")
UPSTASH_TOKEN = os.environ.get("UPSTASH_VECTOR_TOKEN", "")


def bm25_sparse(text: str, k1: float = 1.5, b: float = 0.75) -> dict[int, float]:
    tokens = text.lower().split()
    tf = {}
    for token in tokens:
        tf[token] = tf.get(token, 0) + 1
    scores = {}
    for token, count in tf.items():
        token_hash = hash(token) % (2**31)
        scores[token_hash] = count * (k1 + 1) / (
            count + k1 * (1 - b + b * len(tokens) / 100)
        )
    return scores


def main():
    parser = argparse.ArgumentParser(description="Import BGE-M3 embeddings to Upstash Vector")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no upsert")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size")
    args = parser.parse_args()

    from upstash_vector import Index
    from upstash_vector.types import SparseVector, Vector

    if not UPSTASH_URL or not UPSTASH_TOKEN:
        raise SystemExit(
            "Missing credentials: set UPSTASH_VECTOR_URL and UPSTASH_VECTOR_TOKEN."
        )
    idx = Index(url=UPSTASH_URL, token=UPSTASH_TOKEN)

    print(f"Reading embeddings from {EMBEDDINGS_PATH} ...")
    embeddings = []
    with open(EMBEDDINGS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            embeddings.append(json.loads(line))

    print(f"Loaded {len(embeddings)} embeddings")

    print(f"Reading chunks from {CHUNKS_PATH} ...")
    chunks = {}
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            chunks[chunk["chunk_id"]] = chunk

    print(f"Loaded {len(chunks)} chunks")

    if args.dry_run:
        sample = embeddings[0]
        print(f"Sample chunk_id: {sample['chunk_id']}")
        print(f"Dimensions: {sample['dimensions']}")
        print(f"Model: {sample['model']}")
        print(f"Dense vector length: {len(sample['dense_vector'])}")
        print(f"Sparse vector: {sample['sparse_vector']}")
        print("Dry run complete.")
        return

    total_upserted = 0
    for start in range(0, len(embeddings), args.batch_size):
        batch = embeddings[start : start + args.batch_size]
        batch_num = start // args.batch_size + 1
        total_batches = math.ceil(len(embeddings) / args.batch_size)

        vectors = []
        for emb in batch:
            chunk_id = emb["chunk_id"]
            chunk = chunks.get(chunk_id, {})
            meta = chunk.get("metadata", {})
            doc_meta = meta.get("document", {})
            struct = meta.get("structure", {})
            content = chunk.get("content", "")

            sparse_raw = emb.get("sparse_vector", {})
            sparse_indices = sparse_raw.get("indices", [])
            sparse_values = sparse_raw.get("values", [])

            vectors.append(Vector(
                id=chunk_id,
                vector=emb["dense_vector"],
                sparse_vector=SparseVector(
                    indices=sparse_indices,
                    values=sparse_values,
                ),
                metadata={
                    "chunk_id": chunk_id,
                    "document_id": chunk.get("document_id", ""),
                    "chapter": struct.get("bab") or "",
                    "section": struct.get("bagian") or "",
                    "article": struct.get("pasal") or "",
                    "paragraph": struct.get("paragraf") or "",
                    "page_start": chunk.get("page_start", 0),
                    "page_end": chunk.get("page_end", 0),
                    "text": content[:10000],
                    "retrieval_text": content[:10000],
                    "topics": [],
                    "legal_status": doc_meta.get("regulation_status", "active"),
                    "source_url": doc_meta.get("source_url", ""),
                    "embedding_model": emb.get("model", "BAAI/bge-m3"),
                    "document_title": doc_meta.get("document_title", ""),
                    "section_path": struct.get("section_path", []),
                },
            ))

        print(f"Upserting batch {batch_num}/{total_batches} ({len(vectors)} vectors) ...")
        idx.upsert(vectors=vectors)
        total_upserted += len(vectors)
        print(f"  Total: {total_upserted}")
        time.sleep(0.3)

    print(f"\nDone! Total upserted: {total_upserted} vectors")


if __name__ == "__main__":
    main()
