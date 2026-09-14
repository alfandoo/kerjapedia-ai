"""Export validated pre-embedding chunks for an offline embedding runtime.

Example:
python -m app.services.ingestion.evaluation.export_jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.ingestion.artifacts import ArtifactStore

EXPORT_SCHEMA_VERSION = "kerjapedia-colab-chunks-v1"


@dataclass(frozen=True)
class JsonlExportResult:
    """Immutable summary of a validated Colab embedding export."""

    path: str
    document_count: int
    chunk_count: int
    sha256: str


def export_chunks_jsonl(
    output_root: Path,
    *,
    relative_path: Path = Path("exports/chunks.jsonl"),
) -> JsonlExportResult:
    """Export latest PASS build artifacts as newline-delimited JSON.

    The export intentionally stops before embedding. Every record has a stable
    ``chunk_id`` and ``content`` field for BGE input, plus the complete existing
    provenance payload for a later database/vector import.
    """
    reports_root = output_root / "reports"
    corpus = _read_json(reports_root / "corpus.json")
    if corpus.get("scope") != "through_metadata":
        raise ValueError("Only load-through-metadata evaluation reports may be exported")
    if corpus.get("status") != "PASS":
        raise ValueError("Corpus evaluation must be PASS before export")

    records: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    document_ids: list[str] = []
    for summary in corpus.get("documents", []):
        document_id = _required_string(summary, "document_id")
        report = _read_json(reports_root / f"{document_id}.json")
        if report.get("status") != "PASS":
            raise ValueError(f"Document {document_id} is not PASS")
        if report.get("scope") != "through_metadata":
            raise ValueError(f"Document {document_id} has an invalid evaluation scope")
        build_id = _required_string(report, "build_id")
        chunks_path = output_root / "artifacts" / document_id / build_id / "chunks.json"
        chunks = _read_json(chunks_path)
        if not isinstance(chunks, list):
            raise ValueError(f"{chunks_path} must contain a chunk array")
        document_ids.append(document_id)
        for chunk in chunks:
            record = _validated_record(chunk, document_id)
            chunk_id = record["chunk_id"]
            if chunk_id in seen_chunk_ids:
                raise ValueError(f"Duplicate chunk_id in export: {chunk_id}")
            seen_chunk_ids.add(chunk_id)
            records.append(record)

    if not records:
        raise ValueError("No validated chunks are available for export")
    encoded = b"".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        for record in records
    )
    path = ArtifactStore(output_root).write_bytes(relative_path, encoded)
    return JsonlExportResult(
        path=path,
        document_count=len(document_ids),
        chunk_count=len(records),
        sha256=hashlib.sha256(encoded).hexdigest(),
    )


def _validated_record(chunk: object, document_id: str) -> dict[str, Any]:
    if not isinstance(chunk, dict):
        raise ValueError(f"Chunk for {document_id} is not an object")
    chunk_id = _required_string(chunk, "chunk_id")
    content = _required_string(chunk, "content")
    if chunk.get("document_id") != document_id:
        raise ValueError(f"Chunk {chunk_id} belongs to another document")
    content_hash = _required_string(chunk, "content_hash")
    if hashlib.sha256(content.encode("utf-8")).hexdigest() != content_hash:
        raise ValueError(f"Chunk {chunk_id} has an invalid content hash")
    metadata = chunk.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError(f"Chunk {chunk_id} is missing provenance metadata")
    metadata_document = metadata.get("document")
    metadata_chunk = metadata.get("chunk")
    if (
        not isinstance(metadata_document, dict)
        or metadata_document.get("document_id") != document_id
    ):
        raise ValueError(f"Chunk {chunk_id} has inconsistent document provenance")
    if not isinstance(metadata_chunk, dict) or metadata_chunk.get("chunk_id") != chunk_id:
        raise ValueError(f"Chunk {chunk_id} has inconsistent chunk provenance")
    if metadata_chunk.get("content_hash") != content_hash:
        raise ValueError(f"Chunk {chunk_id} has inconsistent content-hash provenance")
    page_start = chunk.get("page_start")
    page_end = chunk.get("page_end")
    if not isinstance(page_start, int) or not isinstance(page_end, int) or page_start > page_end:
        raise ValueError(f"Chunk {chunk_id} has invalid page provenance")

    # Keep the source artifact's public fields intact; Colab needs only
    # ``content`` and ``chunk_id``, while the nested metadata enables safe
    # association with vectors after the offline embedding step.
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "chunk_id": chunk_id,
        "document_id": document_id,
        "content": content,
        "content_hash": content_hash,
        "page_start": page_start,
        "page_end": page_end,
        "legal_hierarchy": chunk.get("legal_hierarchy", {}),
        "metadata": metadata,
        "parent_chunk_id": chunk.get("parent_chunk_id"),
        "section_path": chunk.get("section_path", []),
        "source": chunk.get("source"),
        "source_url": chunk.get("source_url"),
        "token_count": chunk.get("token_count"),
        "chunk_type": chunk.get("chunk_type"),
        "part_number": chunk.get("part_number"),
        "part_count": chunk.get("part_count"),
    }


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"Required ingestion artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _required_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Missing required field {field}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--path", type=Path, default=Path("exports/chunks.jsonl"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[6]
    output_root = args.output_dir or root / "storage/ingestion/preembedding"
    result = export_chunks_jsonl(output_root, relative_path=args.path)
    print(json.dumps(result.__dict__, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
