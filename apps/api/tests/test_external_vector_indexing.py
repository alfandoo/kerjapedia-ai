from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.ingestion.external_embeddings import (
    DEFAULT_MODEL,
    DEFAULT_REVISION,
    accept_external_embeddings,
)
from app.services.ingestion.external_vector_indexing import (
    ExternalStagingIndexError,
    StagingIndexConfig,
    _is_namespace_not_found,
    stage_external_embeddings,
)


class FakeStagingStore:
    def __init__(self, *, acknowledge_all: bool = True) -> None:
        self.acknowledge_all = acknowledge_all
        self.vectors: dict[str, dict] = {}
        self.clear_calls = 0

    def clear_namespace(self) -> None:
        self.clear_calls += 1
        self.vectors.clear()

    def upsert(self, vectors: list[dict]) -> int:
        for vector in vectors:
            self.vectors[vector["id"]] = vector["metadata"]
        return len(vectors) if self.acknowledge_all else len(vectors) - 1

    def fetch_metadata(self, vector_ids: list[str]) -> dict[str, dict]:
        return {
            vector_id: self.vectors[vector_id]
            for vector_id in vector_ids
            if vector_id in self.vectors
        }

    def namespace_vector_count(self) -> int:
        return len(self.vectors)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    chunks_path = tmp_path / "chunks.jsonl"
    embeddings_path = tmp_path / "embeddings.jsonl"
    colab_manifest_path = tmp_path / "colab.json"
    receipt_path = tmp_path / "receipt.json"
    staging_manifest_path = tmp_path / "staging.json"
    chunks = []
    embeddings = []
    for index in range(2):
        content = f"Pasal {index + 1}\nKetentuan hukum."
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk_id = f"chunk-{index + 1}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "document_id": "UU-1-2020",
                "content": content,
                "content_hash": content_hash,
                "page_start": index + 1,
                "page_end": index + 1,
                "source": "JDIH BPK",
                "source_url": "https://peraturan.bpk.go.id/Details/1",
                "token_count": 7,
                "metadata": {
                    "document": {
                        "document_title": "Undang-Undang Nomor 1 Tahun 2020",
                        "document_type": "UU",
                        "document_number": 1,
                        "year": 2020,
                        "regulation_status": "active",
                        "file_hash": "a" * 64,
                    },
                    "structure": {"pasal": f"Pasal {index + 1}"},
                    "chunk": {"metadata_hash": f"metadata-{index}"},
                    "ingestion": {
                        "ingestion_version": "v1",
                        "parser_version": "v1",
                        "chunker_version": "v1",
                    },
                },
            }
        )
        embeddings.append(
            {
                "chunk_id": chunk_id,
                "content_hash": content_hash,
                "model": DEFAULT_MODEL,
                "model_revision": DEFAULT_REVISION,
                "vector_space": f"{DEFAULT_MODEL}@{DEFAULT_REVISION}:1024",
                "dimensions": 1024,
                "dense_vector": [1.0] + [0.0] * 1023,
                "sparse_vector": {"1": 0.5},
            }
        )
    _write_jsonl(chunks_path, chunks)
    _write_jsonl(embeddings_path, embeddings)
    colab_manifest_path.write_text(
        json.dumps(
            {
                "input_chunks": 2,
                "previously_completed": 0,
                "embedded_this_run": 2,
                "failed": 0,
                "model": DEFAULT_MODEL,
                "model_revision": DEFAULT_REVISION,
                "dimensions": 1024,
            }
        ),
        encoding="utf-8",
    )
    accept_external_embeddings(
        chunks_path=chunks_path,
        embeddings_path=embeddings_path,
        colab_manifest_path=colab_manifest_path,
        receipt_path=receipt_path,
    )
    return chunks_path, embeddings_path, colab_manifest_path, receipt_path, staging_manifest_path


def test_stages_and_verifies_all_external_vectors(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    store = FakeStagingStore()

    result = stage_external_embeddings(
        store=store,
        chunks_path=paths[0],
        embeddings_path=paths[1],
        colab_manifest_path=paths[2],
        import_receipt_path=paths[3],
        staging_manifest_path=paths[4],
        namespace="staging-test",
        config=StagingIndexConfig(batch_size=1, retry_initial_seconds=0),
        sleep=lambda _: None,
    )

    assert result.status == "verified"
    assert result.expected_vector_count == 2
    assert result.verified_vector_count == 2
    assert store.clear_calls == 1
    assert store.vectors["chunk-1"]["publication_status"] == "draft"
    manifest = json.loads(paths[4].read_text(encoding="utf-8"))
    assert manifest["expected_vector_ids"] == ["chunk-1", "chunk-2"]


def test_failed_batch_is_cleaned_and_never_receipted_as_verified(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    store = FakeStagingStore(acknowledge_all=False)

    with pytest.raises(ExternalStagingIndexError, match="did not acknowledge"):
        stage_external_embeddings(
            store=store,
            chunks_path=paths[0],
            embeddings_path=paths[1],
            colab_manifest_path=paths[2],
            import_receipt_path=paths[3],
            staging_manifest_path=paths[4],
            namespace="staging-test",
            config=StagingIndexConfig(batch_size=2, max_retries=0),
        )

    assert store.vectors == {}
    assert store.clear_calls == 2
    assert not paths[4].exists()


def test_missing_staging_namespace_is_treated_as_empty() -> None:
    error = type("NotFound", (Exception,), {"status": 404})("Namespace not found")

    assert _is_namespace_not_found(error)
