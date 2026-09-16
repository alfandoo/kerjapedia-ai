from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.api.routes_ingestion import _advance_version_ingestion_status
from app.models.ingestion import DocumentVersion, IngestionBuild
from app.services.ingestion import database
from app.services.ingestion.builds import (
    IngestionBuildConfig,
    document_metadata_hash,
    make_build_identity,
)
from app.services.ingestion.domain import content_sha256
from app.services.ingestion.embeddings import EmbeddingBatchError, HashEmbeddingProvider
from app.services.ingestion.pipeline import ingest_document
from app.services.ingestion.quality import text_sha256
from app.services.ingestion.schemas import (
    Chunk,
    DocumentMetadata,
    EmbeddedChunk,
    ExtractedPage,
    IngestionResult,
)


class _FakeQuery:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def filter(self, *_args) -> _FakeQuery:
        return self

    def order_by(self, *_args) -> _FakeQuery:
        return self

    def all(self) -> list[object]:
        return self.rows

    def one_or_none(self) -> object | None:
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None


class CountingHashEmbeddingProvider(HashEmbeddingProvider):
    def __init__(self, dimensions: int = 8, *, fail_on_call: int | None = None) -> None:
        super().__init__(dimensions)
        self.calls = 0
        self.fail_on_call = fail_on_call

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise ConnectionError("simulated embedding interruption")
        return super().embed(texts)


def _document(
    root: Path,
    *,
    content: bytes = b"%PDF-1.7\nsource-one\n%%EOF\n",
    title: str = "Peraturan Pemerintah Nomor 35 Tahun 2021",
) -> tuple[Path, DocumentMetadata]:
    source = root / "dataset" / "source.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    document = DocumentMetadata(
        document_id="PP-35-2021",
        title=title,
        short_title="PP 35/2021",
        regulation_type="PP",
        number=35,
        year=2021,
        issuer="Pemerintah Republik Indonesia",
        topics=["pkwt"],
        legal_status="active",
        source_name="JDIH BPK",
        source_url="https://peraturan.bpk.go.id/Details/161904",
        local_file="dataset/source.pdf",
        file_name="source.pdf",
        size_bytes=len(content),
        sha256=digest,
        verification_status="verified",
        source_verification_status="verified",
        legal_review_status="verified",
    )
    manifest = root / "metadata.json"
    manifest.write_text(
        json.dumps({"documents": [document.__dict__]}),
        encoding="utf-8",
    )
    return manifest, document


def _pages(_: Path) -> list[ExtractedPage]:
    text = (
        "BAB III\nKETENTUAN UMUM\nPasal 15\n"
        "(1) Pengusaha wajib memberikan uang kompensasi kepada pekerja/buruh.\n"
        "Pasal 16\n(1) Ketentuan pembayaran dilaksanakan sesuai peraturan."
    )
    return [
        ExtractedPage(
            page_number=1,
            text=text,
            raw_text=text,
            text_length=len(text),
            requires_ocr=False,
            quality_score=1.0,
            disposition="text_extracted",
        )
    ]


def _config(**changes) -> IngestionBuildConfig:
    base = IngestionBuildConfig(
        target_tokens=20,
        max_tokens=35,
        overlap_tokens=4,
        min_merge_tokens=5,
        embedding_batch_size=1,
        embedding_model="local-hash-embedding-v1",
        embedding_revision="deterministic-v1",
        embedding_dimension=8,
        require_native_sparse=False,
        runtime={},
    )
    return replace(base, **changes)


def _ingest(
    root: Path,
    manifest: Path,
    provider: CountingHashEmbeddingProvider,
    config: IngestionBuildConfig,
) -> IngestionResult:
    return ingest_document(
        project_root=root,
        metadata_path=manifest,
        document_id="PP-35-2021",
        output_dir=root / "artifacts",
        embedding_provider=provider,
        build_config=config,
    )


def test_duplicate_ingestion_reuses_complete_build_without_reembedding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _ = _document(tmp_path)
    monkeypatch.setattr("app.services.ingestion.pipeline.extract_pages", _pages)
    provider = CountingHashEmbeddingProvider()
    config = _config()

    first = _ingest(tmp_path, manifest, provider, config)
    calls_after_first = provider.calls
    manifest_path = Path(first.artifacts["build_manifest"])
    original_manifest = manifest_path.read_bytes()
    second = _ingest(tmp_path, manifest, provider, config)

    assert second == first
    assert provider.calls == calls_after_first
    assert manifest_path.read_bytes() == original_manifest
    statistics = first.quality_report["ingestion_statistics"]
    assert statistics["documents_processed"] == 1
    assert statistics["pages_parsed"] == 1
    assert statistics["sections_detected"] > 0
    assert statistics["chunks_generated"] == first.chunk_count
    assert statistics["chunks_embedded"] == first.chunk_count
    assert statistics["chunks_indexed"] == 0
    assert statistics["failed_embeddings"] == 0
    assert statistics["duration_seconds"] >= 0
    evaluation_path = Path(first.artifacts["ingestion_evaluation"])
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    assert evaluation_path.is_file()
    assert evaluation["document_id"] == "PP-35-2021"
    assert evaluation["build_id"] == first.build_id
    assert evaluation["embedding"]["succeeded"] == first.chunk_count
    assert evaluation["indexing"]["evaluated"] is False
    assert (
        tmp_path
        / "artifacts"
        / "reports"
        / "ingestion"
        / "PP-35-2021.json"
    ).is_file()
    assert (
        tmp_path / "artifacts" / "reports" / "ingestion" / "corpus.json"
    ).is_file()


def test_completed_build_cannot_be_force_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _ = _document(tmp_path)
    monkeypatch.setattr("app.services.ingestion.pipeline.extract_pages", _pages)
    provider = CountingHashEmbeddingProvider()
    config = _config()
    completed = _ingest(tmp_path, manifest, provider, config)
    build_manifest = Path(completed.artifacts["build_manifest"])
    original = build_manifest.read_bytes()

    with pytest.raises(RuntimeError, match="immutable"):
        ingest_document(
            project_root=tmp_path,
            metadata_path=manifest,
            document_id="PP-35-2021",
            output_dir=tmp_path / "artifacts",
            embedding_provider=provider,
            build_config=config,
            resume=False,
        )

    assert build_manifest.read_bytes() == original


def test_same_file_with_new_chunker_version_creates_a_distinct_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _ = _document(tmp_path)
    monkeypatch.setattr("app.services.ingestion.pipeline.extract_pages", _pages)
    provider = CountingHashEmbeddingProvider()

    first = _ingest(tmp_path, manifest, provider, _config())
    second = _ingest(
        tmp_path,
        manifest,
        provider,
        _config(chunker_version=_config().chunker_version + "-changed"),
    )

    assert first.version == second.version
    assert first.build_id != second.build_id
    assert Path(first.artifacts["build_manifest"]).is_file()
    assert Path(second.artifacts["build_manifest"]).is_file()


def test_same_source_registered_as_another_document_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, document = _document(tmp_path)
    duplicate = replace(
        document,
        document_id="DUPLICATE-PP-35-2021",
        title="Duplicate registry entry",
    )
    manifest.write_text(
        json.dumps({"documents": [document.__dict__, duplicate.__dict__]}),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.services.ingestion.pipeline.extract_pages", _pages)

    with pytest.raises(ValueError, match="already registered"):
        _ingest(
            tmp_path,
            manifest,
            CountingHashEmbeddingProvider(),
            _config(),
        )

    assert not (tmp_path / "artifacts" / "documents").exists()
    failure_report = json.loads(
        (
            tmp_path
            / "artifacts"
            / "reports"
            / "ingestion"
            / "PP-35-2021.json"
        ).read_text(encoding="utf-8")
    )
    assert failure_report["status"] == "FAIL"
    assert failure_report["document"]["file_readable"] is True
    assert failure_report["document"]["source_error"].startswith("ValueError:")


def test_updated_source_creates_new_version_and_preserves_prior_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_manifest, _ = _document(tmp_path)
    monkeypatch.setattr("app.services.ingestion.pipeline.extract_pages", _pages)
    provider = CountingHashEmbeddingProvider()
    first = _ingest(tmp_path, first_manifest, provider, _config())
    prior_manifest = Path(first.artifacts["build_manifest"])
    prior_bytes = prior_manifest.read_bytes()

    second_manifest, _ = _document(
        tmp_path,
        content=b"%PDF-1.7\nsource-two-official-revision\n%%EOF\n",
    )
    second = _ingest(tmp_path, second_manifest, provider, _config())

    assert first.version != second.version
    assert first.build_id != second.build_id
    assert prior_manifest.read_bytes() == prior_bytes
    assert Path(second.artifacts["build_manifest"]).is_file()


def test_partial_failure_is_not_complete_and_retry_resumes_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, document = _document(tmp_path)
    monkeypatch.setattr("app.services.ingestion.pipeline.extract_pages", _pages)
    stable = _ingest(tmp_path, manifest, CountingHashEmbeddingProvider(), _config())
    stable_manifest = Path(stable.artifacts["build_manifest"])
    stable_bytes = stable_manifest.read_bytes()

    retry_config = _config(
        chunker_version="interrupted-chunker-v3",
        embedding_max_retries=0,
    )
    identity = make_build_identity(
        document.document_id,
        document.sha256,
        retry_config,
        document_metadata_hash(document),
    )
    failed_build = (
        tmp_path
        / "artifacts"
        / "documents"
        / document.document_id
        / f"v{stable.version}"
        / "builds"
        / identity.build_id
    )
    with pytest.raises(EmbeddingBatchError) as error:
        _ingest(
            tmp_path,
            manifest,
            CountingHashEmbeddingProvider(fail_on_call=2),
            retry_config,
        )
    assert error.value.cause_type == "ConnectionError"
    assert error.value.failed_item_ids

    checkpoint = failed_build / "checkpoints" / "embeddings.jsonl"
    assert checkpoint.is_file()
    assert not (failed_build / "metadata" / "build_manifest.json").exists()
    assert stable_manifest.read_bytes() == stable_bytes
    failed_report = json.loads(
        (
            tmp_path
            / "artifacts"
            / "reports"
            / "ingestion"
            / "PP-35-2021.json"
        ).read_text(encoding="utf-8")
    )
    assert failed_report["status"] == "FAIL"
    assert failed_report["embedding"]["failed"] > 0
    assert "Embedding failed" in failed_report["embedding"]["error"]

    retry_provider = CountingHashEmbeddingProvider()
    retried = _ingest(tmp_path, manifest, retry_provider, retry_config)

    assert retried.build_id == identity.build_id
    assert Path(retried.artifacts["build_manifest"]).is_file()
    assert stable_manifest.read_bytes() == stable_bytes
    assert retry_provider.calls >= 1


def test_build_identity_tracks_metadata_and_ignores_topic_order(
    tmp_path: Path,
) -> None:
    _, document = _document(tmp_path)
    reordered = replace(document, topics=["thr", "pkwt"])
    same_topics_different_order = replace(reordered, topics=["pkwt", "thr"])
    renamed = replace(document, title="Judul resmi yang diperbarui")

    assert document_metadata_hash(reordered) == document_metadata_hash(
        same_topics_different_order
    )
    assert document_metadata_hash(document) != document_metadata_hash(renamed)


def test_persistence_rolls_back_the_transaction_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        database,
        "_persist_ingestion_result",
        MagicMock(side_effect=RuntimeError("write interrupted")),
    )

    with pytest.raises(RuntimeError, match="write interrupted"):
        database.persist_ingestion_result(
            session,
            MagicMock(),
            MagicMock(),
            [],
            build_config=_config(),
        )

    session.rollback.assert_called_once_with()
    session.commit.assert_not_called()


def test_persistence_commits_verified_reuse_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        database,
        "_persist_ingestion_result",
        MagicMock(return_value="reused"),
    )

    disposition = database.persist_ingestion_result(
        session,
        MagicMock(),
        MagicMock(),
        [],
        build_config=_config(),
    )

    assert disposition == "reused"
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()


def test_completed_database_materialization_is_verified_and_not_rewritten(
    tmp_path: Path,
) -> None:
    _, document = _document(tmp_path)
    config = _config()
    identity = make_build_identity(
        document.document_id,
        document.sha256,
        config,
        document_metadata_hash(document),
    )
    version = int(document.sha256[:8], 16)
    version_id = f"{document.document_id}-v{version}"
    chunk = Chunk(
        chunk_id=f"{identity.build_id}-chunk-00001",
        document_id=document.document_id,
        chapter="BAB III",
        section=None,
        article="Pasal 15",
        paragraph="Ayat (1)",
        page_start=1,
        page_end=1,
        text="Pengusaha wajib memberikan kompensasi.",
        token_count=5,
        topics=["pkwt"],
        legal_status="active",
        source_url=document.source_url,
        build_id=identity.build_id,
        retrieval_text="Pasal 15\nPengusaha wajib memberikan kompensasi.",
    )
    embedded = EmbeddedChunk(
        chunk=chunk,
        embedding_model=config.embedding_model,
        embedding=[1.0] + [0.0] * 7,
        sparse_embedding={1: 1.0},
        embedding_revision=config.embedding_revision,
        retrieval_text_sha256=text_sha256(chunk.retrieval_text or chunk.text),
    )
    artifact_manifest = {"chunks": {"sha256": "c" * 64}}
    result = IngestionResult(
        document_id=document.document_id,
        version=version,
        status="completed",
        artifacts={"chunks": "chunks.json"},
        chunk_count=1,
        pages_processed=1,
        requires_review=False,
        warnings=[],
        build_id=identity.build_id,
        config_hash=identity.config_hash,
        artifact_manifest=artifact_manifest,
    )
    version_row = SimpleNamespace(
        version_id=version_id,
        document_id=document.document_id,
        sha256=document.sha256,
    )
    build = SimpleNamespace(
        build_id=identity.build_id,
        version_id=version_id,
        source_sha256=document.sha256,
        metadata_hash=identity.metadata_hash,
        config_hash=identity.config_hash,
        status="completed",
        artifact_manifest=artifact_manifest,
    )
    stored_chunk = SimpleNamespace(
        chunk_id=chunk.chunk_id,
        chunk_index=0,
        content_hash=content_sha256(chunk.text),
    )
    stored_embedding = SimpleNamespace(
        chunk_id=chunk.chunk_id,
        embedding_model=embedded.embedding_model,
        embedding_revision=embedded.embedding_revision,
        dimensions=len(embedded.embedding),
        retrieval_text_sha256=embedded.retrieval_text_sha256,
    )
    session = MagicMock()

    def query(model):
        if model is database.DocumentVersion:
            return _FakeQuery([version_row])
        if model is database.DocumentChunk:
            return _FakeQuery([stored_chunk])
        if model is database.ChunkEmbedding:
            return _FakeQuery([stored_embedding])
        raise AssertionError(f"unexpected query model: {model}")

    session.query.side_effect = query
    session.get.side_effect = lambda model, _key: (
        build if model is database.IngestionBuild else None
    )

    disposition = database._persist_ingestion_result(
        session,
        document,
        result,
        [embedded],
        build_config=config,
    )

    assert disposition == "reused"
    session.merge.assert_not_called()
    session.execute.assert_not_called()
    session.add_all.assert_not_called()


def test_database_constraints_cover_source_and_build_identity() -> None:
    version_constraints = {
        constraint.name for constraint in DocumentVersion.__table__.constraints
    }
    build_constraints = {
        constraint.name for constraint in IngestionBuild.__table__.constraints
    }

    assert "uq_document_versions_source_sha256" in version_constraints
    assert "uq_ingestion_build_fingerprint" in build_constraints
    fingerprint = next(
        constraint
        for constraint in IngestionBuild.__table__.constraints
        if constraint.name == "uq_ingestion_build_fingerprint"
    )
    assert {column.name for column in fingerprint.columns} == {
        "version_id",
        "config_hash",
        "metadata_hash",
        "embedding_model",
        "embedding_revision",
    }


def test_failed_retry_does_not_downgrade_a_completed_version() -> None:
    completed = SimpleNamespace(is_current=False, ingestion_status="completed")
    pending = SimpleNamespace(is_current=False, ingestion_status="queued")
    current = SimpleNamespace(is_current=True, ingestion_status="completed")

    _advance_version_ingestion_status(completed, "failed")
    _advance_version_ingestion_status(pending, "failed")
    _advance_version_ingestion_status(current, "failed")

    assert completed.ingestion_status == "completed"
    assert pending.ingestion_status == "failed"
    assert current.ingestion_status == "completed"
