from datetime import UTC, datetime, timedelta

from app.services.rag.indexing import (
    FenceRegistry,
    InMemoryVectorStore,
    build_filter,
    build_release_manifest,
    clear_namespace_guarded,
    estimate_metadata_size,
    fit_metadata,
    load_verified_artifact,
    verify_release_manifest,
    write_artifact_manifest,
    write_verified,
)
from app.services.rag.indexing.schemas import StoredVector


def make_vector(chunk_id: str, first: float = 1.0) -> StoredVector:
    return StoredVector(
        id=chunk_id, values=(first, 0.0), metadata={"chunk_id": chunk_id}
    )


def test_memory_store_ranks_by_cosine() -> None:
    store = InMemoryVectorStore()
    store.upsert(
        [make_vector("dekat", 1.0), make_vector("jauh", 0.0)], namespace="ns"
    )

    assert store.query([1.0, 0.0], top_k=2, namespace="ns")[0][0] == "dekat"
    assert store.count("ns") == 2


def test_verified_write_accepts_matching_vectors() -> None:
    store = InMemoryVectorStore()
    vectors = [make_vector("a"), make_vector("b")]

    report = write_verified(store, vectors, "ns", sleep=lambda _: None)

    assert report.rolled_back is False
    assert (report.upserted, report.verified) == (2, 2)
    assert report.worst_cosine == 1.0
    assert store.count("ns") == 2


def test_verified_write_rolls_back_corrupted_vectors() -> None:
    class CorruptingStore(InMemoryVectorStore):
        def fetch(self, ids, namespace):
            found = super().fetch(ids, namespace)
            return {
                chunk_id: StoredVector(
                    id=chunk_id, values=(0.0, 1.0), metadata={"chunk_id": chunk_id}
                )
                for chunk_id in found
            }

    store = CorruptingStore()

    report = write_verified(
        store, [make_vector("a")], "ns", sleep=lambda _: None
    )

    assert report.rolled_back is True
    assert store.count("ns") == 0


def test_oversized_metadata_sheds_bulk_first() -> None:
    metadata = {
        "chunk_id": "c1",
        "parent_text": "x" * 50000,
        "text": "aturan upah.",
        "retrieval_text": "aturan upah.",
    }

    fitted, shed = fit_metadata(metadata, limit_bytes=1000)

    assert "parent_text" in shed
    assert "parent_text" not in fitted
    assert estimate_metadata_size(fitted) <= 1000


def test_namespace_deletion_previews_before_destroying() -> None:
    store = InMemoryVectorStore()
    store.upsert([make_vector("a"), make_vector("b")], namespace="ns")

    preview = clear_namespace_guarded(store, "ns", confirm=False)

    assert preview.confirmed is False
    assert preview.vector_count == 2
    assert store.count("ns") == 2

    receipt = clear_namespace_guarded(store, "ns", confirm=True)

    assert receipt.confirmed is True
    assert sorted(receipt.backed_up_ids) == ["a", "b"]
    assert store.count("ns") == 0


def test_release_manifest_detects_drift() -> None:
    manifest = build_release_manifest(
        index_name="idx",
        namespace="ns",
        build_id="b1",
        model_space="BAAI/bge-m3@rev:1024",
        vector_count=2,
        document_ids=["PP-35-2021"],
        created_by="pipeline",
    )

    assert verify_release_manifest(manifest, vector_count=2, model_space=manifest.model_space) == []
    problems = verify_release_manifest(manifest, vector_count=1, model_space="other@rev:8")
    assert len(problems) == 2


def test_artifact_load_refuses_tampered_files(tmp_path) -> None:
    manifest_path = write_artifact_manifest(
        tmp_path, {"chunks.json": b"[{...}]"}
    )

    assert manifest_path.exists()
    assert load_verified_artifact(tmp_path, "chunks.json") == b"[{...}]"
    (tmp_path / "chunks.json").write_bytes(b"tampered")
    try:
        load_verified_artifact(tmp_path, "chunks.json")
    except ValueError as exc:
        assert "checksum mismatch" in str(exc)
    else:
        raise AssertionError("tampered artifact must be refused")


def test_write_fence_refuses_second_owner_until_expiry() -> None:
    registry = FenceRegistry()
    now = datetime.now(UTC)

    assert registry.acquire("PP-35-2021", "build-a", now) is True
    assert registry.acquire("PP-35-2021", "build-b", now) is False
    assert registry.release("PP-35-2021", "build-b") is False
    assert registry.release("PP-35-2021", "build-a") is True
    assert registry.acquire("PP-35-2021", "build-b", now) is True

    assert registry.acquire("PP-35-2021", "build-c", now) is False
    later = now + timedelta(seconds=7200)
    assert registry.acquire("PP-35-2021", "build-c", later) is True


def test_filter_builder_combines_static_and_new_dimensions() -> None:
    pinecone_filter = build_filter(
        article="Pasal 15",
        regulation_type="PP",
        number=35,
        legal_statuses=["active", "amended"],
        published_only=True,
        effective_on="2024-01-01",
        segment_kinds=["substantive"],
        freshness_states=["fresh", "due"],
        topics=["pkwt"],
    )

    assert pinecone_filter["article"] == {"$eq": "Pasal 15"}
    assert pinecone_filter["effective_date"] == {"$lte": "2024-01-01"}
    assert pinecone_filter["segment_kind"] == {"$in": ["substantive"]}
    assert pinecone_filter["freshness_state"] == {"$in": ["fresh", "due"]}
    assert build_filter() is None
