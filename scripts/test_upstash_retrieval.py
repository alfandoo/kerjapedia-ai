"""Sanity-test Upstash hybrid retrieval with realistic KerjaPedia queries.

Sends RAW query text to Upstash (hosted dense + BM25 hybrid), then prints
rank, hybrid score, chunk id, source, page and a text preview per hit.

Usage (from the repository root)::

    apps/api/.venv/Scripts/python scripts/test_upstash_retrieval.py
    apps/api/.venv/Scripts/python scripts/test_upstash_retrieval.py "Siapa yang berhak memperoleh THR?"
    apps/api/.venv/Scripts/python scripts/test_upstash_retrieval.py --top-k 10 --raw
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

DEFAULT_QUERIES = [
    "Apakah pekerja PKWT memperoleh uang kompensasi?",
    "Berapa lama batas maksimal PKWT?",
    "Siapa yang berhak memperoleh THR?",
    "Apa perbedaan JHT, JKM, dan JP?",
    "Kapan perusahaan wajib membentuk P2K3?",
    "PP Nomor 35 Tahun 2021 Pasal 15",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--namespace", type=str, default=None)
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw hybrid matches without the rerank pipeline.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    from app.core.config import settings
    from app.services.retrieval.upstash_vector_store import (
        UpstashVectorConfig,
        UpstashVectorStore,
    )

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
    queries = [args.query] if args.query else DEFAULT_QUERIES
    for query in queries:
        print(f"\n=== Query: {query}")
        started = time.monotonic()
        if args.raw:
            matches = store.query(query, top_k=args.top_k)
            latency_ms = round((time.monotonic() - started) * 1000, 1)
            print(f"({len(matches)} hybrid matches, {latency_ms} ms)")
            for rank, match in enumerate(matches, start=1):
                meta = match.get("metadata") or {}
                preview = str((match.get("data") or meta.get("text") or "")[:200]).replace(
                    "\n", " "
                )
                print(
                    f"#{rank} score={match['score']:.4f} id={match['id']} "
                    f"source={meta.get('document_id', '')} "
                    f"page={meta.get('page_start', '')} article={meta.get('article', '')}"
                )
                print(f"    {preview}")
        else:
            response = store.search(query, top_k=args.top_k)
            latency_ms = round((time.monotonic() - started) * 1000, 1)
            print(
                f"({len(response.results)} results, {latency_ms} ms, "
                f"refuse={response.should_refuse}, warnings={response.warnings})"
            )
            for rank, item in enumerate(response.results, start=1):
                doc = item.document
                preview = str(doc.retrieval_text[:200]).replace("\n", " ")
                print(
                    f"#{rank} final={item.final_score:.4f} id={doc.chunk_id} "
                    f"source={doc.document_id} page={doc.page_start} "
                    f"article={doc.article or ''}"
                )
                print(f"    {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
