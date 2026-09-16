"""Synchronize an accepted offline BGE artifact to PostgreSQL provenance rows.

Vectors remain in the immutable JSONL artifact and verified Pinecone namespace.
This module never activates a release or changes retrieval configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.ingestion import (
    ChunkEmbedding,
    Document,
    DocumentChunk,
    DocumentVersion,
    IngestionBuild,
)
from app.services.ingestion.external_embeddings import (
    DEFAULT_DIMENSIONS,
    DEFAULT_MODEL,
    DEFAULT_REVISION,
    IMPORT_SCHEMA_VERSION,
)

POSTGRES_IMPORT_SCHEMA_VERSION = "kerjapedia-external-postgres-import-v1"
IMPORT_STATUS = "external_verified"


class PineconeVerifier(Protocol):
    def namespace_vector_count(self) -> int: ...


@dataclass(frozen=True)
class ExternalPostgresImportResult:
    schema_version: str
    status: str
    namespace: str
    document_count: int
    chunk_count: int
    build_ids: dict[str, str]
    chunks_sha256: str
    embeddings_sha256: str
    staging_manifest_sha256: str


def import_external_bge_snapshot(
    *,
    session: Session,
    chunks_path: Path,
    import_receipt_path: Path,
    staging_manifest_path: Path,
    verifier: PineconeVerifier,
) -> ExternalPostgresImportResult:
    """Validate first, then atomically add an external BGE snapshot.

    Existing canonical IDs are never overwritten: a rerun must be byte-identical
    and is treated as a no-op; a conflicting ID fails the transaction.
    """
    chunks = _load_chunks(chunks_path)
    receipt = _load_object(import_receipt_path, "embedding import receipt")
    staging = _load_object(staging_manifest_path, "staging index manifest")
    _validate_manifests(receipt, staging, chunks_path, len(chunks))
    _verify_pinecone(verifier, chunks, staging)
    versions = _validated_versions(session, chunks)
    now = datetime.now(UTC)
    builds = _ensure_builds(session, versions, chunks, receipt, staging, now)
    _insert_missing_rows(session, chunks, versions, builds, str(receipt["embeddings_sha256"]), now)
    session.flush()
    _verify_postgres(session, chunks, builds, receipt)
    return ExternalPostgresImportResult(
        schema_version=POSTGRES_IMPORT_SCHEMA_VERSION,
        status="verified",
        namespace=str(staging["namespace"]),
        document_count=len(versions),
        chunk_count=len(chunks),
        build_ids={key: value.build_id for key, value in builds.items()},
        chunks_sha256=str(receipt["chunks_sha256"]),
        embeddings_sha256=str(receipt["embeddings_sha256"]),
        staging_manifest_sha256=_sha256(staging_manifest_path),
    )


def _load_chunks(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Canonical chunks artifact is missing: {path}")
    chunks, seen = [], set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid chunks JSONL at line {line_number}") from exc
        _validate_chunk(chunk, line_number)
        chunk_id = str(chunk["chunk_id"])
        if chunk_id in seen:
            raise ValueError(f"Duplicate canonical chunk ID: {chunk_id}")
        seen.add(chunk_id)
        chunks.append(chunk)
    if not chunks:
        raise ValueError("Canonical chunks artifact is empty")
    return chunks


def _validate_chunk(chunk: object, line_number: int) -> None:
    if not isinstance(chunk, dict):
        raise ValueError(f"Chunk must be an object at line {line_number}")
    required = ("chunk_id", "document_id", "content", "content_hash", "metadata")
    if any(not chunk.get(key) for key in required):
        raise ValueError(f"Chunk line {line_number} is incomplete")
    if hashlib.sha256(str(chunk["content"]).encode()).hexdigest() != chunk["content_hash"]:
        raise ValueError(f"Invalid content hash at line {line_number}")
    metadata = chunk["metadata"]
    if not isinstance(metadata, dict) or not all(
        isinstance(metadata.get(key), dict)
        for key in ("document", "structure", "chunk", "ingestion")
    ):
        raise ValueError(f"Chunk provenance is incomplete at line {line_number}")
    if (
        metadata["document"].get("document_id") != chunk["document_id"]
        or metadata["chunk"].get("chunk_id") != chunk["chunk_id"]
    ):
        raise ValueError(f"Chunk provenance identity mismatch at line {line_number}")
    if metadata["chunk"].get("content_hash") != chunk["content_hash"]:
        raise ValueError(f"Chunk provenance hash mismatch at line {line_number}")
    if (
        not isinstance(chunk.get("page_start"), int)
        or not isinstance(chunk.get("page_end"), int)
        or chunk["page_start"] < 1
        or chunk["page_end"] < chunk["page_start"]
    ):
        raise ValueError(f"Invalid page range at line {line_number}")


def _validate_manifests(
    receipt: dict[str, Any], staging: dict[str, Any], chunks_path: Path, count: int
) -> None:
    if (
        receipt.get("schema_version") != IMPORT_SCHEMA_VERSION
        or receipt.get("status") != "accepted"
    ):
        raise ValueError("External embedding receipt is not accepted")
    if (
        receipt.get("model") != DEFAULT_MODEL
        or receipt.get("model_revision") != DEFAULT_REVISION
        or receipt.get("dimensions") != DEFAULT_DIMENSIONS
    ):
        raise ValueError("External embedding receipt model is not accepted")
    if receipt.get("chunk_count") != count or receipt.get("chunks_sha256") != _sha256(chunks_path):
        raise ValueError("External embedding receipt does not match canonical chunks")
    if (
        staging.get("status") != "verified"
        or staging.get("expected_vector_count") != count
        or staging.get("verified_vector_count") != count
    ):
        raise ValueError("Staging index manifest is incomplete")
    if staging.get("source_embedding_sha256") != receipt.get("embeddings_sha256"):
        raise ValueError("Staging index does not match accepted embedding artifact")


def _verify_pinecone(
    verifier: PineconeVerifier, chunks: list[dict[str, Any]], staging: dict[str, Any]
) -> None:
    """Check the live namespace against the prior exhaustive staging receipt.

    ``staging_index_manifest.json`` is written only after the staging indexer
    fetches every vector ID and verifies its metadata. Repeating that full
    fetch may be selected by a future audit command; this importer uses the
    immutable manifest plus a live namespace-count check to avoid a provider
    SDK hang during a relational-only synchronization.
    """
    if verifier.namespace_vector_count() != len(chunks):
        raise ValueError("Pinecone namespace count does not match canonical chunks")
    expected_ids = staging.get("expected_vector_ids")
    if not isinstance(expected_ids, list) or set(expected_ids) != {
        str(chunk["chunk_id"]) for chunk in chunks
    }:
        raise ValueError("Staging manifest IDs do not match canonical chunks")


def _validated_versions(
    session: Session, chunks: list[dict[str, Any]]
) -> dict[str, DocumentVersion]:
    hashes: dict[str, str] = {}
    for chunk in chunks:
        document_id = str(chunk["document_id"])
        source_hash = chunk["metadata"]["document"].get("file_hash")
        if not isinstance(source_hash, str) or len(source_hash) != 64:
            raise ValueError(f"Invalid source checksum: {document_id}")
        if document_id in hashes and hashes[document_id] != source_hash:
            raise ValueError(f"Multiple source checksums: {document_id}")
        hashes[document_id] = source_hash
    current = {
        row.document_id: row
        for row in session.query(DocumentVersion)
        .filter(DocumentVersion.document_id.in_(hashes))
        .all()
        if row.is_current
    }
    if set(current) != set(hashes):
        raise ValueError(
            "Missing current DocumentVersion: " + ", ".join(sorted(set(hashes) - set(current)))
        )
    for document_id, version in current.items():
        if version.sha256 != hashes[document_id]:
            raise ValueError(f"Source checksum mismatch: {document_id}")
        if (
            version.publication_status,
            version.source_verification_status,
            version.legal_review_status,
            version.ingestion_status,
        ) != ("published", "verified", "verified", "completed"):
            raise ValueError(f"DocumentVersion is not approved: {document_id}")
    return current


def _ensure_builds(
    session: Session,
    versions: dict[str, DocumentVersion],
    chunks: list[dict[str, Any]],
    receipt: dict[str, Any],
    staging: dict[str, Any],
    now: datetime,
) -> dict[str, IngestionBuild]:
    by_document: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        by_document.setdefault(str(chunk["document_id"]), []).append(chunk)
    config = {
        "schema_version": POSTGRES_IMPORT_SCHEMA_VERSION,
        "embedding_model": DEFAULT_MODEL,
        "embedding_revision": DEFAULT_REVISION,
        "embedding_dimension": DEFAULT_DIMENSIONS,
        "chunks_sha256": receipt["chunks_sha256"],
        "embeddings_sha256": receipt["embeddings_sha256"],
        "staging_namespace": staging["namespace"],
        "staging_manifest_checksum": staging["vector_manifest_checksum"],
    }
    config_hash = _hash(config)
    builds: dict[str, IngestionBuild] = {}
    for document_id, version in versions.items():
        document = session.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document row is missing: {document_id}")
        metadata_hash = _hash(
            {
                "document_id": document.document_id,
                "title": document.title,
                "regulation_type": document.regulation_type,
                "number": document.number,
                "year": document.year,
                "issuer": document.issuer,
                "topics": sorted(document.topics or []),
                "source_sha256": version.sha256,
                "source_url": version.source_url,
            }
        )
        build_fingerprint = {
            "document_id": document_id,
            "source_sha256": version.sha256,
            "metadata_hash": metadata_hash,
            "config_hash": config_hash,
        }
        build_id = f"extb_{_hash(build_fingerprint)[:32]}"
        build = session.get(IngestionBuild, build_id)
        first = by_document[document_id][0]["metadata"]["ingestion"]
        if build is None:
            build = IngestionBuild(
                build_id=build_id,
                version_id=version.version_id,
                document_id=document_id,
                source_sha256=version.sha256,
                metadata_hash=metadata_hash,
                pipeline_version=str(first["ingestion_version"]),
                config_hash=config_hash,
                pipeline_config=config,
                parser_version=str(first["parser_version"]),
                chunker_version=str(first["chunker_version"]),
                ocr_engine="external-artifact",
                embedding_model=DEFAULT_MODEL,
                embedding_revision=DEFAULT_REVISION,
                status="completed",
                review_status="pending",
                quality_report={
                    "external_import": "verified",
                    "chunk_count": len(by_document[document_id]),
                },
                artifact_manifest={
                    "external_embedding_receipt": receipt,
                    "staging_index_manifest": staging,
                },
                page_dispositions={},
                review_notes=(
                    "External BGE snapshot requires the normal build-review "
                    "approval before a release."
                ),
                completed_at=now,
            )
            session.add(build)
        elif (
            build.version_id,
            build.source_sha256,
            build.config_hash,
            build.embedding_model,
            build.embedding_revision,
        ) != (version.version_id, version.sha256, config_hash, DEFAULT_MODEL, DEFAULT_REVISION):
            raise ValueError(f"External build provenance conflict: {build_id}")
        builds[document_id] = build
    session.flush()
    return builds


def _insert_missing_rows(
    session: Session,
    chunks: list[dict[str, Any]],
    versions: dict[str, DocumentVersion],
    builds: dict[str, IngestionBuild],
    artifact_hash: str,
    now: datetime,
) -> None:
    expected_ids = {str(chunk["chunk_id"]) for chunk in chunks}
    for ordinal, chunk in enumerate(chunks):
        chunk_id, document_id = str(chunk["chunk_id"]), str(chunk["document_id"])
        structure, metadata = chunk["metadata"]["structure"], chunk["metadata"]["chunk"]
        build, version = builds[document_id], versions[document_id]
        existing = session.get(DocumentChunk, chunk_id)
        if existing is not None:
            if (
                existing.build_id,
                existing.document_id,
                existing.version_id,
                existing.content_hash,
                existing.metadata_hash,
            ) != (
                build.build_id,
                document_id,
                version.version_id,
                chunk["content_hash"],
                metadata["metadata_hash"],
            ):
                raise ValueError(f"Canonical chunk ID conflicts with existing data: {chunk_id}")
        else:
            parent = metadata.get("parent_chunk_id")
            if parent and parent not in expected_ids:
                raise ValueError(f"Missing canonical parent chunk: {parent}")
            section = (
                " / ".join(
                    filter(
                        None,
                        [
                            _prefix(structure.get("bagian"), "Bagian "),
                            _prefix(structure.get("paragraf"), "Paragraf "),
                        ],
                    )
                )
                or None
            )
            session.add(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    version_id=version.version_id,
                    build_id=build.build_id,
                    chapter=_prefix(structure.get("bab"), "BAB "),
                    section=section,
                    article=_prefix(structure.get("pasal"), "Pasal "),
                    paragraph=_prefix(structure.get("ayat"), "Ayat (", suffix=")"),
                    page_start=chunk["page_start"],
                    page_end=chunk["page_end"],
                    token_count=int(chunk.get("token_count") or 0),
                    text=chunk["content"],
                    retrieval_text=chunk["content"],
                    chunk_type=str(chunk.get("chunk_type") or "substantive"),
                    artifact_checksum=artifact_hash,
                    parent_chunk_id=parent,
                    chunk_index=int(metadata.get("chunk_index", ordinal)),
                    legal_node_id=structure.get("legal_node_id"),
                    section_path=list(
                        chunk.get("section_path") or structure.get("section_path") or []
                    ),
                    content_hash=chunk["content_hash"],
                    metadata_hash=metadata["metadata_hash"],
                    provenance=chunk["metadata"],
                    payload=chunk,
                    created_at=now,
                    updated_at=now,
                )
            )
        embedding = session.get(ChunkEmbedding, chunk_id)
        if embedding is not None:
            if (
                embedding.embedding,
                embedding.embedding_model,
                embedding.embedding_revision,
                embedding.dimensions,
                embedding.embedding_artifact_sha256,
                embedding.import_status,
            ) != (
                None,
                DEFAULT_MODEL,
                DEFAULT_REVISION,
                DEFAULT_DIMENSIONS,
                artifact_hash,
                IMPORT_STATUS,
            ):
                raise ValueError(f"Canonical embedding ID conflicts with existing data: {chunk_id}")
        else:
            session.add(
                ChunkEmbedding(
                    chunk_id=chunk_id,
                    build_id=build.build_id,
                    embedding_model=DEFAULT_MODEL,
                    embedding_revision=DEFAULT_REVISION,
                    dimensions=DEFAULT_DIMENSIONS,
                    vector_norm=None,
                    embedding=None,
                    sparse_embedding=None,
                    retrieval_text_sha256=chunk["content_hash"],
                    embedding_artifact_sha256=artifact_hash,
                    import_status=IMPORT_STATUS,
                )
            )


def _verify_postgres(
    session: Session,
    chunks: list[dict[str, Any]],
    builds: dict[str, IngestionBuild],
    receipt: dict[str, Any],
) -> None:
    expected = {str(chunk["chunk_id"]) for chunk in chunks}
    rows = session.query(DocumentChunk).filter(DocumentChunk.chunk_id.in_(expected)).all()
    embeddings = session.query(ChunkEmbedding).filter(ChunkEmbedding.chunk_id.in_(expected)).all()
    if len(rows) != len(expected) or len(embeddings) != len(expected):
        raise RuntimeError("PostgreSQL reconciliation count failed")
    for row in rows:
        if (
            hashlib.sha256(row.text.encode()).hexdigest() != row.content_hash
            or row.build_id != builds[row.document_id].build_id
        ):
            raise RuntimeError(f"PostgreSQL chunk reconciliation failed: {row.chunk_id}")
    for row in embeddings:
        if (
            row.embedding,
            row.embedding_model,
            row.embedding_revision,
            row.dimensions,
            row.embedding_artifact_sha256,
            row.import_status,
        ) != (
            None,
            DEFAULT_MODEL,
            DEFAULT_REVISION,
            DEFAULT_DIMENSIONS,
            receipt["embeddings_sha256"],
            IMPORT_STATUS,
        ):
            raise RuntimeError(f"PostgreSQL embedding reconciliation failed: {row.chunk_id}")


def _prefix(value: object, prefix: str, suffix: str = "") -> str | None:
    return f"{prefix}{value}{suffix}" if isinstance(value, str) and value else None


def _hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def main() -> None:
    from app.services.ingestion.external_vector_indexing import PineconeStagingStore

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--staging-manifest", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[5]
    embedding_dir = root / "storage/ingestion/embeddings/BAAI-bge-m3" / DEFAULT_REVISION
    manifest_path = args.staging_manifest or embedding_dir / "staging_index_manifest.json"
    staging = _load_object(manifest_path, "staging index manifest")
    with SessionLocal() as session:
        result = import_external_bge_snapshot(
            session=session,
            chunks_path=args.chunks or root / "storage/ingestion/preembedding/exports/chunks.jsonl",
            import_receipt_path=args.receipt or embedding_dir / "embedding_import_manifest.json",
            staging_manifest_path=manifest_path,
            verifier=PineconeStagingStore(
                api_key=settings.pinecone_api_key or "",
                index_name=settings.pinecone_index_name,
                namespace=str(staging["namespace"]),
            ),
        )
        session.commit()
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
