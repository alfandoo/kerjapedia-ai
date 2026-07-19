from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.db.session import create_session
from app.services.ingestion.embeddings import HashEmbeddingProvider, OpenAIEmbeddingProvider
from app.services.ingestion.metadata import load_manifest
from app.services.ingestion.pipeline import ingest_document


def project_root_from_api_dir() -> Path:
    return Path(__file__).resolve().parents[5]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run KerjaPedia document ingestion.")
    parser.add_argument("--document-id", help="Document ID from dataset/metadata.json.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Ingest all documents in metadata manifest.",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="Path to dataset metadata manifest.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Artifact output directory.",
    )
    parser.add_argument(
        "--embedding-provider",
        choices=["hash", "openai"],
        default="hash",
        help="Embedding provider. Use hash for offline/local development.",
    )
    parser.add_argument(
        "--persist-db",
        action="store_true",
        help="Persist document, chunk, embedding, and job metadata to PostgreSQL.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    project_root = project_root_from_api_dir()
    metadata_path = args.metadata or project_root / "dataset" / "metadata.json"
    output_dir = args.output_dir or project_root / "storage" / "ingestion"

    if not args.all and not args.document_id:
        parser.error("Provide --document-id or --all.")

    if args.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for --embedding-provider openai.")
        provider = OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model_name="text-embedding-3-small",
        )
    else:
        provider = HashEmbeddingProvider()

    manifest = load_manifest(metadata_path)
    document_ids = (
        [document.document_id for document in manifest["documents"]]
        if args.all
        else [args.document_id]
    )

    results = [
        ingest_document(
            project_root=project_root,
            metadata_path=metadata_path,
            document_id=document_id,
            output_dir=output_dir,
            embedding_provider=provider,
            database_session_factory=create_session if args.persist_db else None,
        )
        for document_id in document_ids
        if document_id is not None
    ]

    print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
