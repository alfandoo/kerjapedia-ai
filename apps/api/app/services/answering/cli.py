from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from app.core.config import settings
from app.services.providers import (
    answer_generator_from_settings,
    pinecone_store_from_settings,
    upstash_vector_store_from_settings,
)
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.store import load_artifact_documents


def project_root_from_api_dir() -> Path:
    return settings.project_root or Path(__file__).resolve().parents[5]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a grounded local answer.")
    parser.add_argument("query", help="Natural language query.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=None,
        help="Path to storage/ingestion.",
    )
    parser.add_argument(
        "--vector-store",
        choices=["artifact", "pinecone", "upstash_vector"],
        default=None,
        help="Retrieval backend. Defaults to VECTOR_STORE.",
    )
    parser.add_argument(
        "--llm-provider",
        choices=["local", "openrouter", "groq"],
        default=None,
        help="Answer generation backend. Defaults to LLM_PROVIDER.",
    )
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    project_root = project_root_from_api_dir()
    storage_root = args.storage_root or project_root / "storage" / "ingestion"
    vector_store = args.vector_store or settings.vector_store
    if vector_store == "pinecone":
        retrieval = pinecone_store_from_settings(settings).search(args.query, top_k=args.top_k)
    elif vector_store == "upstash_vector":
        retrieval = upstash_vector_store_from_settings(settings).search(
            args.query, top_k=args.top_k
        )
    else:
        documents = load_artifact_documents(storage_root)
        retrieval = RetrievalEngine(documents=documents, top_k=args.top_k).search(
            args.query,
            top_k=args.top_k,
        )
    generator = answer_generator_from_settings(settings, args.llm_provider)
    response = generator.generate(args.query, retrieval)
    print(json.dumps(asdict(response), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
