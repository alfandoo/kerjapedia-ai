from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.store import load_artifact_documents


def project_root_from_api_dir() -> Path:
    return Path(__file__).resolve().parents[5]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search local ingestion artifacts.")
    parser.add_argument("query", help="Natural language query.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=None,
        help="Path to storage/ingestion.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    project_root = project_root_from_api_dir()
    storage_root = args.storage_root or project_root / "storage" / "ingestion"
    documents = load_artifact_documents(storage_root)
    engine = RetrievalEngine(documents=documents, top_k=args.top_k)
    response = engine.search(args.query, top_k=args.top_k)
    print(json.dumps(asdict(response), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
