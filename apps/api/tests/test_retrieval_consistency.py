from datetime import UTC, datetime

from app.services.rag.embedding.schemas import EmbeddingConfig
from app.services.rag.indexing.schemas import ReleaseManifest
from app.services.rag.retrieval.consistency import (
    check_release_against_provider,
)


def test_identical_fingerprints_match() -> None:
    config = EmbeddingConfig(model_name="BAAI/bge-m3", model_revision="rev1", dimensions=1024)
    manifest = ReleaseManifest(
        index_name="i", namespace="ns", build_id="b",
        model_space="BAAI/bge-m3@rev1:1024",
        vector_count=1, document_ids=("d",),
    )
    compatible, detail = check_release_against_provider(manifest, config)
    assert compatible is True
    assert detail is None


def test_diverged_fingerprint_raises() -> None:
    bad = EmbeddingConfig(
        provider="hash", model_name="local-hash-embedding-v1",
        dimensions=1024, allow_unpinned_revision=True,
    )
    manifest = ReleaseManifest(
        index_name="i", namespace="ns", build_id="b",
        model_space="BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181:1024",
        vector_count=4739, document_ids=("PP-35-2021",),
    )
    compatible, detail = check_release_against_provider(manifest, bad)
    assert compatible is False
    assert "local-hash-embedding-v1" in detail


def test_legacy_space_fingerprint_is_detected() -> None:
    legacy = EmbeddingConfig(
        provider="hash", model_name="local-hash-embedding-v1",
        dimensions=1024, model_revision="unversioned",
        allow_unpinned_revision=True,
    )
    manifest = ReleaseManifest(
        index_name="kerjapedia-regulations",
        namespace="production",
        build_id="b",
        model_space="local-hash-embedding-v1@unversioned:1024",
        vector_count=4739,
        document_ids=("PP-35-2021", "UU-13-2003"),
        created_at=datetime.now(UTC),
        created_by="system",
    )
    compatible, detail = check_release_against_provider(manifest, legacy)
    assert compatible is True  # same (wrong) space: consistent, detectable
    assert "hash" in manifest.model_space
