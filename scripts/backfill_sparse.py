"""Backfill native BGE-M3 sparse values for a Pinecone namespace.

A past metadata-only sync upserted records without ``sparse_values`` and,
because Pinecone upsert replaces the whole record, wiped the sparse
channel index-wide. This script restores it:

- dense values and metadata are reused untouched (no ranking regression
  risk on the dense channel; same model revision as the build),
- only ``sparse_values`` (native BGE lexical weights) are added back,
- a checkpoint file makes reruns resume where they stopped.

Usage (from repo root, API venv active):
    .venv/Scripts/python.exe scripts/backfill_sparse.py \
        --namespace staging-bge-m3-3a779f061d1932ba8603 --dry-run
    .venv/Scripts/python.exe scripts/backfill_sparse.py \
        --namespace staging-bge-m3-3a779f061d1932ba8603 --limit 3
    .venv/Scripts/python.exe scripts/backfill_sparse.py \
        --namespace staging-bge-m3-3a779f061d1932ba8603
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

LIST_TOP_K = 10000


def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).get("done", []))


def save_checkpoint(path: Path, done: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"done": sorted(done)}), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--embed-batch", type=int, default=8)
    parser.add_argument("--fetch-batch", type=int, default=100)
    parser.add_argument("--upsert-batch", type=int, default=100)
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv is not None:
        load_dotenv(REPO_ROOT / ".env")

    from pinecone import Pinecone

    from app.core.config import settings
    from app.services.ingestion.embeddings import BGEM3EmbeddingProvider

    if not settings.pinecone_api_key:
        raise SystemExit("PINECONE_API_KEY is missing (repo .env not loaded?).")

    checkpoint = args.checkpoint or (
        REPO_ROOT / "tmp" / f"backfill_sparse_{args.namespace}.json"
    )
    done = load_checkpoint(checkpoint)

    index = Pinecone(api_key=settings.pinecone_api_key).Index(
        settings.pinecone_index_name
    )
    listing = index.query(
        namespace=args.namespace,
        vector=[0.0] * settings.embedding_dimension,
        top_k=LIST_TOP_K,
        include_metadata=False,
        include_values=False,
    )
    all_ids = [match["id"] for match in listing.get("matches", [])]
    if len(all_ids) >= LIST_TOP_K:
        raise SystemExit("Namespace exceeds single-listing capacity; paginate first.")
    remaining = [vid for vid in sorted(all_ids) if vid not in done]
    if args.limit is not None:
        remaining = remaining[: args.limit]
    print(
        f"namespace={args.namespace} total={len(all_ids)} "
        f"done={len(done)} remaining={len(remaining)}",
        flush=True,
    )
    if not remaining:
        print("Nothing to do.", flush=True)
        return

    provider = BGEM3EmbeddingProvider(
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimension,
        require_native_sparse=True,
        model_revision=settings.embedding_model_revision,
        batch_size=args.embed_batch,
    )

    started = time.monotonic()
    processed = 0
    for start in range(0, len(remaining), args.fetch_batch):
        batch_ids = remaining[start : start + args.fetch_batch]
        fetched = index.fetch(ids=batch_ids, namespace=args.namespace)["vectors"]
        texts: list[str] = []
        usable_ids: list[str] = []
        for vid in batch_ids:
            record = fetched.get(vid, {})
            metadata = record.get("metadata", {}) or {}
            text = (metadata.get("retrieval_text") or metadata.get("text") or "").strip()
            if not text:
                print(f"  skip {vid}: no text in metadata", flush=True)
                done.add(vid)
                continue
            texts.append(text)
            usable_ids.append(vid)
        if not texts:
            save_checkpoint(checkpoint, done)
            continue
        batch = provider.embed_hybrid(texts)
        for vid, sparse in zip(usable_ids, batch.sparse, strict=True):
            if not sparse:
                raise SystemExit(f"Empty native sparse for {vid}; aborting.")
        if args.dry_run:
            for vid, sparse in zip(usable_ids, batch.sparse, strict=True):
                print(
                    f"  dry-run {vid}: sparse_terms={len(sparse)} "
                    f"mass={round(sum(sparse.values()), 3)}",
                    flush=True,
                )
            return
        vectors = []
        for vid in usable_ids:
            record = fetched[vid]
            sparse = batch.sparse[usable_ids.index(vid)]
            vectors.append(
                {
                    "id": vid,
                    "values": record["values"],
                    "sparse_values": {
                        "indices": sorted(sparse),
                        "values": [sparse[i] for i in sorted(sparse)],
                    },
                    "metadata": record.get("metadata", {}),
                }
            )
        for offset in range(0, len(vectors), args.upsert_batch):
            chunk = vectors[offset : offset + args.upsert_batch]
            response = index.upsert(vectors=chunk, namespace=args.namespace)
            acknowledged = getattr(response, "upserted_count", None)
            if acknowledged is None and isinstance(response, dict):
                acknowledged = response.get("upserted_count")
            if acknowledged is None or int(acknowledged) != len(chunk):
                raise SystemExit(f"Upsert not fully acknowledged: {acknowledged}.")
        done.update(usable_ids)
        save_checkpoint(checkpoint, done)
        processed += len(usable_ids)
        elapsed = time.monotonic() - started
        rate = processed / elapsed if elapsed else 0.0
        print(
            f"  {processed}/{len(remaining)} vectors "
            f"({rate:.2f}/s, elapsed {elapsed:.0f}s)",
            flush=True,
        )
    print(f"Done. Checkpoint: {checkpoint}", flush=True)


if __name__ == "__main__":
    main()
