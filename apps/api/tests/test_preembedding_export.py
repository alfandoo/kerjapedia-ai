from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.ingestion.evaluation.export_jsonl import export_chunks_jsonl


def _chunk(document_id: str = "UU-2-2004") -> dict:
    content = "Pasal 80\nCukup jelas."
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {
        "chunk_id": "UU-2-2004-chunk-001",
        "document_id": document_id,
        "content": content,
        "content_hash": content_hash,
        "page_start": 97,
        "page_end": 97,
        "legal_hierarchy": {"pasal": "80"},
        "metadata": {
            "document": {"document_id": document_id},
            "chunk": {"chunk_id": "UU-2-2004-chunk-001", "content_hash": content_hash},
        },
        "parent_chunk_id": None,
        "section_path": ["Penjelasan", "Pasal 80"],
        "source": "JDIH",
        "source_url": "https://example.test/uu-2",
        "token_count": 5,
        "chunk_type": "pasal",
        "part_number": 1,
        "part_count": 1,
    }


def _write_fixture(root: Path, *, status: str = "PASS") -> None:
    reports = root / "reports"
    artifact = root / "artifacts" / "UU-2-2004" / "pre_test"
    reports.mkdir(parents=True)
    artifact.mkdir(parents=True)
    (reports / "corpus.json").write_text(
        json.dumps(
            {
                "status": status,
                "scope": "through_metadata",
                "documents": [{"document_id": "UU-2-2004", "status": status}],
            }
        ),
        encoding="utf-8",
    )
    (reports / "UU-2-2004.json").write_text(
        json.dumps({"status": status, "scope": "through_metadata", "build_id": "pre_test"}),
        encoding="utf-8",
    )
    (artifact / "chunks.json").write_text(json.dumps([_chunk()]), encoding="utf-8")


def test_export_writes_validated_jsonl_for_colab(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    result = export_chunks_jsonl(tmp_path)

    lines = Path(result.path).read_text(encoding="utf-8").splitlines()
    assert result.document_count == 1
    assert result.chunk_count == 1
    assert json.loads(lines[0])["content"] == "Pasal 80\nCukup jelas."
    assert json.loads(lines[0])["metadata"]["document"]["document_id"] == "UU-2-2004"


def test_export_rejects_non_passing_corpus(tmp_path: Path) -> None:
    _write_fixture(tmp_path, status="FAIL")
    with pytest.raises(ValueError, match="Corpus evaluation must be PASS"):
        export_chunks_jsonl(tmp_path)


def test_export_rejects_invalid_content_hash(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    chunks_path = tmp_path / "artifacts" / "UU-2-2004" / "pre_test" / "chunks.json"
    payload = json.loads(chunks_path.read_text(encoding="utf-8"))
    payload[0]["content_hash"] = "invalid"
    chunks_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid content hash"):
        export_chunks_jsonl(tmp_path)
