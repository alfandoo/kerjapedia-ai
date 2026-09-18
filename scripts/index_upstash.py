"""Index pre-embedding chunks into Upstash Vector (hosted embeddings).

Reads the existing ``chunks.jsonl`` export -- no PDF parsing, no cleaning,
no chunking, no local embedding. Raw chunk text is sent to Upstash, which
produces dense vectors (``open-ai/text-embedding-3-small``) and sparse
vectors (BM25) server-side on its HYBRID index.

Usage (from the repository root)::

    python scripts/index_upstash.py --dry-run
    python scripts/index_upstash.py --limit 100
    python scripts/index_upstash.py
    python scripts/index_upstash.py --namespace staging --batch-size 50

Credentials come from the environment (never from CLI args or logs)::

    UPSTASH_VECTOR_REST_URL=...
    UPSTASH_VECTOR_REST_TOKEN=...
    # legacy names still accepted: UPSTASH_VECTOR_URL / UPSTASH_VECTOR_TOKEN
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

DEFAULT_CHUNKS_PATH = (
    REPO_ROOT / "storage" / "ingestion" / "preembedding" / "exports" / "chunks.jsonl"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-path", type=Path, default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--namespace", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip the Upstash index configuration sanity check.",
    )
    parser.add_argument(
        "--no-verify-hash",
        action="store_true",
        help="Do not compare content against content_hash.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    from app.core.config import settings
    from app.services.ingestion.upstash_indexing import (
        load_preembedding_chunks,
        transform_chunks,
        validate_chunks,
    )
    from app.services.retrieval.upstash_vector_store import (
        UpstashVectorConfig,
        UpstashVectorStore,
    )

    started = time.monotonic()
    if args.limit is not None and args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2
    if args.batch_size < 1:
        print("--batch-size must be positive", file=sys.stderr)
        return 2
    if not args.chunks_path.exists():
        print(f"Chunks file not found: {args.chunks_path}", file=sys.stderr)
        return 2

    raw_chunks = load_preembedding_chunks(args.chunks_path)
    print(f"Loaded {len(raw_chunks)} raw chunks from {args.chunks_path}")
    if args.limit is not None:
        raw_chunks = raw_chunks[: args.limit]
        print(f"Limited to first {len(raw_chunks)} chunks (--limit {args.limit})")

    valid, report = validate_chunks(raw_chunks, verify_content_hash=not args.no_verify_hash)
    records = transform_chunks(valid)
    print(
        f"Validation: total={report.total} valid={report.valid} "
        f"skipped={report.skipped} duplicates={len(report.duplicate_ids)}"
    )
    if report.skipped_reasons:
        for reason in sorted(report.skipped_reasons):
            print(f"  skipped[{reason}]={report.skipped_reasons[reason]}")
    if report.duplicate_ids[:5]:
        print(f"  duplicate_ids(sample)={report.duplicate_ids[:5]}")

    if args.dry_run:
        if records:
            sample = records[0]
            print(f"Sample id: {sample['chunk_id']}")
            print(f"Sample text chars: {len(sample['text'])}")
            print(f"Sample metadata keys: {sorted(sample['metadata'])}")
        print("Dry run complete: nothing uploaded.")
        return 0

    if not settings.upstash_vector_url or not settings.upstash_vector_token:
        print(
            "Missing Upstash credentials: set UPSTASH_VECTOR_REST_URL and "
            "UPSTASH_VECTOR_REST_TOKEN.",
            file=sys.stderr,
        )
        return 2

    store = UpstashVectorStore(
        config=UpstashVectorConfig(
            url=settings.upstash_vector_url,
            token=settings.upstash_vector_token,
            dimension=settings.upstash_vector_dimension,
            namespace=args.namespace or settings.upstash_vector_namespace,
        ),
    )
    if not args.skip_verify:
        index_report = store.verify_index(strict=True)
        print(
            "Index verified: "
            f"dense={index_report.dense_embedding_model} "
            f"sparse={index_report.sparse_embedding_model} "
            f"similarity={index_report.similarity_function} "
            f"dimension={index_report.dimension} "
            f"vectors={index_report.vector_count}"
        )

    uploaded = 0
    failed: list[str] = []
    total_batches = max((len(records) + args.batch_size - 1) // args.batch_size, 1)
    for start in range(0, len(records), args.batch_size):
        batch = records[start : start + args.batch_size]
        batch_no = start // args.batch_size + 1
        try:
            store.upsert_chunks(batch, batch_size=len(batch))
        except Exception as exc:  # noqa: BLE001 - record ids, keep going
            print(f"Batch {batch_no}/{total_batches} FAILED: {exc}", file=sys.stderr)
            failed.extend(item["chunk_id"] for item in batch)
            continue
        uploaded += len(batch)
        print(f"Batch {batch_no}/{total_batches}: uploaded {uploaded}/{len(records)}")

    elapsed = round(time.monotonic() - started, 1)
    print(
        f"Summary: total={report.total} valid={report.valid} "
        f"skipped={report.skipped} failed={len(failed)} uploaded={uploaded} "
        f"elapsed_s={elapsed}"
    )
    if failed[:10]:
        print(f"failed_ids(sample)={failed[:10]}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
