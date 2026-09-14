from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.ingestion.external_embeddings import accept_external_embeddings


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    content = "Pasal 1\nKetentuan ini berlaku."
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    chunks = tmp_path / "chunks.jsonl"
    embeddings = tmp_path / "embeddings.jsonl"
    manifest = tmp_path / "manifest.json"
    receipt = tmp_path / "receipt.json"
    _write_jsonl(
        chunks,
        [{"chunk_id": "chunk-1", "content": content, "content_hash": content_hash}],
    )
    _write_jsonl(
        embeddings,
        [
            {
                "chunk_id": "chunk-1",
                "content_hash": content_hash,
                "model": "BAAI/bge-m3",
                "model_revision": "test-revision",
                "vector_space": "BAAI/bge-m3@test-revision:2",
                "dimensions": 2,
                "dense_vector": [0.6, 0.8],
                "sparse_vector": {"1": 0.5},
            }
        ],
    )
    manifest.write_text(
        json.dumps(
            {
                "input_chunks": 1,
                "previously_completed": 0,
                "embedded_this_run": 1,
                "failed": 0,
                "model": "BAAI/bge-m3",
                "model_revision": "test-revision",
                "dimensions": 2,
            }
        ),
        encoding="utf-8",
    )
    return chunks, embeddings, manifest, receipt


def _accept(tmp_path: Path):
    chunks, embeddings, manifest, receipt = _fixture(tmp_path)
    return accept_external_embeddings(
        chunks_path=chunks,
        embeddings_path=embeddings,
        colab_manifest_path=manifest,
        receipt_path=receipt,
        expected_revision="test-revision",
        expected_dimensions=2,
    )


def test_accepts_exact_complete_external_embedding_artifact(tmp_path: Path) -> None:
    result = _accept(tmp_path)

    assert result.status == "accepted"
    assert result.chunk_count == 1
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["embeddings_sha256"] == result.embeddings_sha256


def test_rejects_embedding_content_hash_mismatch(tmp_path: Path) -> None:
    chunks, embeddings, manifest, receipt = _fixture(tmp_path)
    payload = json.loads(embeddings.read_text(encoding="utf-8"))
    payload["content_hash"] = "not-the-canonical-hash"
    _write_jsonl(embeddings, [payload])

    with pytest.raises(ValueError, match="Chunk/content hash mismatch"):
        accept_external_embeddings(
            chunks_path=chunks,
            embeddings_path=embeddings,
            colab_manifest_path=manifest,
            receipt_path=receipt,
            expected_revision="test-revision",
            expected_dimensions=2,
        )
    assert not receipt.exists()


def test_rejects_duplicate_or_wrong_dimension_vectors(tmp_path: Path) -> None:
    chunks, embeddings, manifest, receipt = _fixture(tmp_path)
    payload = json.loads(embeddings.read_text(encoding="utf-8"))
    _write_jsonl(embeddings, [payload, payload])

    with pytest.raises(ValueError, match="Duplicate embedded chunk_id"):
        accept_external_embeddings(
            chunks_path=chunks,
            embeddings_path=embeddings,
            colab_manifest_path=manifest,
            receipt_path=receipt,
            expected_revision="test-revision",
            expected_dimensions=2,
        )


def test_rejects_colab_manifest_with_failures(tmp_path: Path) -> None:
    chunks, embeddings, manifest, receipt = _fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["failed"] = 1
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="failed embeddings"):
        accept_external_embeddings(
            chunks_path=chunks,
            embeddings_path=embeddings,
            colab_manifest_path=manifest,
            receipt_path=receipt,
            expected_revision="test-revision",
            expected_dimensions=2,
        )
