from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.config import settings
from app.db.session import create_session
from app.services.ingestion.builds import (
    build_config_from_settings,
    validate_candidate_runtime,
)
from app.services.ingestion.metadata import load_manifest
from app.services.ingestion.pipeline import ingest_document
from app.services.ingestion.retry import RetryPolicy, run_with_retry
from app.services.providers import embedding_provider_from_settings


def project_root_from_api_dir() -> Path:
    return settings.project_root or Path(__file__).resolve().parents[5]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run KerjaPedia document ingestion.")
    parser.add_argument(
        "--document-id",
        action="append",
        help="Document ID from dataset/metadata.json. Repeat to ingest multiple documents.",
    )
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
        choices=["hash", "bge_m3", "openai"],
        default=None,
        help="Embedding provider. Defaults to EMBEDDING_PROVIDER.",
    )
    parser.add_argument(
        "--persist-db",
        action="store_true",
        help="Persist document, build, chunk, embedding, and job metadata to PostgreSQL.",
    )
    parser.add_argument(
        "--release-candidate",
        action="store_true",
        help="Require the pinned BGE-M3, native sparse, OCR, and database release gates.",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Resume embedding checkpoints and return an identical completed build as a no-op.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Retry transient failures this many times. Defaults to 2.",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=1.0,
        help="Initial exponential-backoff delay in seconds.",
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
    if args.release_candidate and not args.persist_db:
        parser.error("--release-candidate requires --persist-db.")
    if (
        args.release_candidate
        and (args.embedding_provider or settings.embedding_provider) != "bge_m3"
    ):
        parser.error("--release-candidate requires --embedding-provider bge_m3.")
    if args.max_retries < 0 or args.retry_delay < 0:
        parser.error("--max-retries and --retry-delay must not be negative.")

    provider = embedding_provider_from_settings(
        settings,
        args.embedding_provider,
        require_native_sparse=(True if args.release_candidate else None),
    )
    build_config = build_config_from_settings(
        settings,
        provider,
        release_candidate=args.release_candidate,
    )
    if args.release_candidate:
        validate_candidate_runtime(build_config)

    manifest = load_manifest(metadata_path)
    document_ids = (
        [document.document_id for document in manifest["documents"]]
        if args.all
        else args.document_id
    )

    def ingest(document_id: str):
        return run_with_retry(
            lambda: ingest_document(
                project_root=project_root,
                metadata_path=metadata_path,
                document_id=document_id,
                output_dir=output_dir,
                embedding_provider=provider,
                database_session_factory=create_session if args.persist_db else None,
                build_config=build_config,
                resume=args.resume,
            ),
            policy=RetryPolicy(
                max_retries=args.max_retries,
                initial_delay_seconds=args.retry_delay,
            ),
            on_retry=lambda attempt, delay, exc: print(
                (
                    f"ingestion_retry document_id={document_id} attempt={attempt} "
                    f"delay_seconds={delay:g} error={type(exc).__name__}"
                ),
                file=sys.stderr,
            ),
        )

    results = [ingest(document_id) for document_id in document_ids]
    print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
