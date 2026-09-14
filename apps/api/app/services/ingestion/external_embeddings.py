"""Validate offline BGE-M3 artifacts before they are eligible for indexing.

This module is intentionally an ingestion boundary: it accepts the Colab
artifact, checks it against the canonical chunks export, and emits an immutable
acceptance receipt. It does not call Pinecone, mutate retrieval state, or write
database rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.services.ingestion.artifacts import ArtifactStore

IMPORT_SCHEMA_VERSION = "kerjapedia-external-embedding-import-v1"
DEFAULT_MODEL = "BAAI/bge-m3"
DEFAULT_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
DEFAULT_DIMENSIONS = 1024


@dataclass(frozen=True)
class ExternalEmbeddingImportResult:
    """Verification result for a complete external embedding artifact."""

    schema_version: str
    status: str
    chunk_count: int
    dimensions: int
    model: str
    model_revision: str
    chunks_path: str
    chunks_sha256: str
    embeddings_path: str
    embeddings_sha256: str
    colab_manifest_path: str
    colab_manifest_sha256: str
    receipt_path: str


def accept_external_embeddings(
    *,
    chunks_path: Path,
    embeddings_path: Path,
    colab_manifest_path: Path,
    receipt_path: Path,
    expected_model: str = DEFAULT_MODEL,
    expected_revision: str = DEFAULT_REVISION,
    expected_dimensions: int = DEFAULT_DIMENSIONS,
) -> ExternalEmbeddingImportResult:
    """Accept a complete, exactly matching external embedding run.

    A failure raises ``ValueError`` and does not write the receipt. The receipt
    is the only artifact that makes the supplied vectors eligible for a later
    vector-indexing stage.
    """
    expected_chunks = _load_canonical_chunks(chunks_path)
    run_manifest = _load_object(colab_manifest_path, "Colab manifest")
    _validate_run_manifest(
        run_manifest,
        expected_count=len(expected_chunks),
        model=expected_model,
        revision=expected_revision,
        dimensions=expected_dimensions,
    )
    _validate_embedding_rows(
        embeddings_path,
        expected_chunks=expected_chunks,
        model=expected_model,
        revision=expected_revision,
        dimensions=expected_dimensions,
    )

    receipt = ExternalEmbeddingImportResult(
        schema_version=IMPORT_SCHEMA_VERSION,
        status="accepted",
        chunk_count=len(expected_chunks),
        dimensions=expected_dimensions,
        model=expected_model,
        model_revision=expected_revision,
        chunks_path=chunks_path.as_posix(),
        chunks_sha256=_sha256(chunks_path),
        embeddings_path=embeddings_path.as_posix(),
        embeddings_sha256=_sha256(embeddings_path),
        colab_manifest_path=colab_manifest_path.as_posix(),
        colab_manifest_sha256=_sha256(colab_manifest_path),
        receipt_path=receipt_path.as_posix(),
    )
    # ArtifactStore provides atomic write/promotion semantics for the receipt.
    ArtifactStore(receipt_path.parent).write_json(Path(receipt_path.name), asdict(receipt))
    return receipt


def _load_canonical_chunks(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"Canonical chunks artifact is missing: {path}")
    chunks: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            payload = _load_line(line, path, line_number)
            chunk_id = _required_text(payload, "chunk_id", line_number)
            content = _required_text(payload, "content", line_number)
            content_hash = _required_text(payload, "content_hash", line_number)
            if hashlib.sha256(content.encode("utf-8")).hexdigest() != content_hash:
                raise ValueError(f"Invalid canonical content_hash at line {line_number}")
            if chunk_id in chunks:
                raise ValueError(f"Duplicate canonical chunk_id: {chunk_id}")
            chunks[chunk_id] = content_hash
    if not chunks:
        raise ValueError("Canonical chunks artifact is empty")
    return chunks


def _validate_embedding_rows(
    path: Path,
    *,
    expected_chunks: dict[str, str],
    model: str,
    revision: str,
    dimensions: int,
) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"External embeddings artifact is missing: {path}")
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            payload = _load_line(line, path, line_number)
            chunk_id = _required_text(payload, "chunk_id", line_number)
            if chunk_id in seen_ids:
                raise ValueError(f"Duplicate embedded chunk_id: {chunk_id}")
            seen_ids.add(chunk_id)
            if expected_chunks.get(chunk_id) != payload.get("content_hash"):
                raise ValueError(f"Chunk/content hash mismatch: {chunk_id}")
            if payload.get("model") != model or payload.get("model_revision") != revision:
                raise ValueError(f"Embedding model mismatch: {chunk_id}")
            if payload.get("dimensions") != dimensions:
                raise ValueError(f"Embedding dimension metadata mismatch: {chunk_id}")
            expected_space = f"{model}@{revision}:{dimensions}"
            if payload.get("vector_space") != expected_space:
                raise ValueError(f"Embedding vector-space mismatch: {chunk_id}")
            _validate_dense(payload.get("dense_vector"), chunk_id, dimensions)
            _validate_sparse(payload.get("sparse_vector"), chunk_id)
    if seen_ids != set(expected_chunks):
        missing = sorted(set(expected_chunks) - seen_ids)
        unexpected = sorted(seen_ids - set(expected_chunks))
        details = ", ".join((missing + unexpected)[:5])
        raise ValueError(f"External embedding IDs do not match canonical chunks: {details}")


def _validate_run_manifest(
    payload: dict[str, Any],
    *,
    expected_count: int,
    model: str,
    revision: str,
    dimensions: int,
) -> None:
    if payload.get("failed") != 0:
        raise ValueError("Colab manifest reports failed embeddings")
    if payload.get("input_chunks") != expected_count:
        raise ValueError("Colab manifest input_chunks does not match canonical chunks")
    completed = payload.get("previously_completed")
    embedded = payload.get("embedded_this_run")
    if not isinstance(completed, int) or not isinstance(embedded, int):
        raise ValueError("Colab manifest is missing embedding counts")
    if completed + embedded != expected_count:
        raise ValueError("Colab manifest does not account for every chunk")
    if payload.get("model") != model or payload.get("model_revision") != revision:
        raise ValueError("Colab manifest model identity is not accepted")
    if payload.get("dimensions") != dimensions:
        raise ValueError("Colab manifest dimensions are not accepted")


def _validate_dense(raw_vector: object, chunk_id: str, dimensions: int) -> None:
    if not isinstance(raw_vector, list) or len(raw_vector) != dimensions:
        raise ValueError(f"Invalid dense vector dimensions: {chunk_id}")
    try:
        values = [float(value) for value in raw_vector]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Non-numeric dense vector: {chunk_id}") from exc
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"Non-finite dense vector: {chunk_id}")
    if math.sqrt(sum(value * value for value in values)) == 0:
        raise ValueError(f"Zero dense vector: {chunk_id}")


def _validate_sparse(raw_vector: object, chunk_id: str) -> None:
    if not isinstance(raw_vector, dict) or not raw_vector:
        raise ValueError(f"Missing native sparse vector: {chunk_id}")
    try:
        values = [float(value) for value in raw_vector.values()]
        keys_are_valid = all(str(int(key)) == str(key) for key in raw_vector)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid sparse vector: {chunk_id}") from exc
    if not keys_are_valid or not all(math.isfinite(value) for value in values):
        raise ValueError(f"Invalid sparse vector: {chunk_id}")


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _load_line(line: str, path: Path, line_number: int) -> dict[str, Any]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSONL row must be an object at {path}:{line_number}")
    return payload


def _required_text(payload: dict[str, Any], key: str, line_number: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Missing {key} at line {line_number}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path)
    parser.add_argument("--embeddings", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[5]
    embedding_dir = root / "storage/ingestion/embeddings/BAAI-bge-m3" / DEFAULT_REVISION
    result = accept_external_embeddings(
        chunks_path=args.chunks or root / "storage/ingestion/preembedding/exports/chunks.jsonl",
        embeddings_path=args.embeddings or embedding_dir / "bge_m3_embeddings.jsonl",
        colab_manifest_path=args.manifest or embedding_dir / "bge_m3_embedding_manifest.json",
        receipt_path=args.receipt or embedding_dir / "embedding_import_manifest.json",
    )
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
