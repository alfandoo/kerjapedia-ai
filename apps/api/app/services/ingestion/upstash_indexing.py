"""Map pre-embedding chunks to Upstash hosted-embedding records.

Source of truth is the existing ``chunks.jsonl`` export
(``storage/ingestion/preembedding/exports/chunks.jsonl``): no PDF parsing,
no cleaning, no chunking and no local embedding happen here. Each record
carries raw text in ``text``; Upstash produces dense
(``open-ai/text-embedding-3-small``) and sparse (BM25) vectors server-side.

Logical record::

    {
        "chunk_id": "unique-deterministic-chunk-id",
        "text": "raw text chunk",
        "metadata": {...flat, JSON-serializable...},
    }
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ChunkValidationReport:
    total: int = 0
    valid: int = 0
    skipped: int = 0
    duplicate_ids: list[str] = field(default_factory=list)
    skipped_reasons: dict[str, int] = field(default_factory=dict)

    def note_skipped(self, reason: str) -> None:
        self.skipped += 1
        self.skipped_reasons[reason] = self.skipped_reasons.get(reason, 0) + 1


def load_preembedding_chunks(path: Path) -> list[dict[str, Any]]:
    """Read raw JSONL chunks; one dict per non-blank line."""
    chunks: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: chunk must be a JSON object")
            chunks.append(record)
    return chunks


def validate_chunks(
    raw_chunks: list[dict[str, Any]],
    *,
    verify_content_hash: bool = True,
) -> tuple[list[dict[str, Any]], ChunkValidationReport]:
    """Keep well-formed chunks; count skips instead of failing the run."""
    report = ChunkValidationReport(total=len(raw_chunks))
    valid: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for record in raw_chunks:
        chunk_id = record.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            report.note_skipped("empty_id")
            continue
        if chunk_id in seen_ids:
            report.duplicate_ids.append(chunk_id)
            report.note_skipped("duplicate_id")
            continue
        content = record.get("content")
        if not isinstance(content, str) or not content.strip():
            report.note_skipped("empty_text")
            continue
        if verify_content_hash:
            expected = record.get("content_hash")
            actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if isinstance(expected, str) and expected and expected != actual:
                report.note_skipped("content_hash_mismatch")
                continue
        try:
            json.dumps(record.get("metadata") if isinstance(record.get("metadata"), dict) else {})
        except (TypeError, ValueError):
            report.note_skipped("unserializable_metadata")
            continue
        seen_ids.add(chunk_id)
        valid.append(record)
    report.valid = len(valid)
    return valid, report


def transform_chunk(record: dict[str, Any]) -> dict[str, Any]:
    """Map one pre-embedding chunk to an Upstash upsert record.

    Existing ``chunk_id`` values are already unique and deterministic
    (``{DOCUMENT}-{content-hash-prefix}``), so they are preserved as-is
    to keep indexing idempotent. No governance metadata is fabricated here:
    publication/verification/current flags are authoritative in Neon
    (``DocumentVersion``) and enforced by the Neon-backed governance filter
    at retrieval time. Fields absent from the source are omitted, never
    defaulted to plausible values, except pipeline bookkeeping
    (``embedding_model`` marker).
    """
    chunk_id = str(record["chunk_id"])
    text = str(record["content"])
    metadata_raw = record.get("metadata") or {}
    document = metadata_raw.get("document") or {}
    structure = metadata_raw.get("structure") or {}
    chunk_info = metadata_raw.get("chunk") or {}
    section_path = structure.get("section_path") or record.get("section_path") or []

    metadata: dict[str, Any] = {
        "chunk_id": chunk_id,
        "document_id": str(record.get("document_id") or document.get("document_id") or ""),
        "title": str(document.get("document_title") or ""),
        "document_type": str(document.get("document_type") or ""),
        "number": document.get("document_number"),
        "year": document.get("year"),
        "source": str(record.get("source") or ""),
        "source_url": str(record.get("source_url") or document.get("source_url") or ""),
        "page_start": int(record.get("page_start") or structure.get("page_start") or 0),
        "page_end": int(
            record.get("page_end")
            or structure.get("page_end")
            or record.get("page_start")
            or 0
        ),
        "chunk_index": chunk_info.get("chunk_index", record.get("part_number", 0)),
        "chapter": structure.get("bab"),
        "section": structure.get("bagian") or " / ".join(section_path) or None,
        "article": structure.get("pasal"),
        "paragraph": structure.get("paragraf") or structure.get("ayat"),
        "token_count": record.get("token_count", 0),
        "content_hash": str(record.get("content_hash") or ""),
        "legal_status": str(document.get("regulation_status") or "active"),
        "text": text[:12_000],
        "retrieval_text": text[:12_000],
        "embedding_model": "upstash-hosted:text-embedding-3-small",
    }
    if isinstance(section_path, list) and section_path:
        metadata["section_path"] = [str(item) for item in section_path]
    return {
        "chunk_id": chunk_id,
        "text": text,
        "metadata": {key: value for key, value in metadata.items() if value is not None},
    }


def transform_chunks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [transform_chunk(record) for record in records]
