from app.services.rag.embedding import (
    HashEmbeddingProvider,
    check_vector,
    duplicate_vector_groups,
    effective_config,
    embed_indexed,
    lexical_sparse_vector,
    norm_stats,
    vector_space_id,
    verify_index_compatibility,
    with_retries,
)
from app.services.rag.embedding.schemas import EmbeddedChunk, EmbeddingConfig


def test_hash_provider_is_quarantined_to_tests() -> None:
    provider = HashEmbeddingProvider(dimensions=8)

    assert len(provider.embed(["kompensasi pkwt"])[0]) == 8
    try:
        HashEmbeddingProvider(dimensions=8, purpose="production")
    except ValueError as exc:
        assert "quarantined" in str(exc)
    else:
        raise AssertionError("hash provider must refuse non-test purpose")


def test_unpinned_revision_refuses_to_build() -> None:
    try:
        effective_config(EmbeddingConfig(model_revision=""))
    except ValueError as exc:
        assert "pinned" in str(exc)
    else:
        raise AssertionError("unpinned revision must be refused")

    allowed = effective_config(
        EmbeddingConfig(model_revision="abc123", allow_unpinned_revision=True)
    )
    assert allowed.model_revision == "abc123"


def test_vector_space_fingerprint_identifies_model_revision_dim() -> None:
    config = EmbeddingConfig(
        model_name="BAAI/bge-m3", model_revision="rev1", dimensions=1024
    )

    assert vector_space_id(config) == "BAAI/bge-m3@rev1:1024"
    assert vector_space_id(config) != vector_space_id(
        EmbeddingConfig(
            model_name="BAAI/bge-m3", model_revision="rev2", dimensions=1024
        )
    )


def test_checkpoint_resume_keeps_finished_vectors(tmp_path) -> None:
    provider = HashEmbeddingProvider(dimensions=8)
    items = [(f"chunk-{index}", f"teks ketentuan {index}") for index in range(5)]

    first = embed_indexed(items, provider, batch_size=2, checkpoint_dir=tmp_path)
    assert len(first) == 5
    assert sorted(tmp_path.glob("batch-*.json"))

    second = embed_indexed(items, provider, batch_size=2, checkpoint_dir=tmp_path)
    assert second == first


def test_vector_quality_rejects_unphysical_vectors() -> None:
    good = EmbeddedChunk(chunk_id="a", vector=(1.0, 0.0))
    zero = EmbeddedChunk(chunk_id="b", vector=(0.0, 0.0))
    bad = EmbeddedChunk(chunk_id="c", vector=(float("nan"), 0.0))
    short = EmbeddedChunk(chunk_id="d", vector=(1.0,))

    assert check_vector(good, 2) == []
    assert [issue.code for issue in check_vector(zero, 2)] == ["zero_vector"]
    assert [issue.code for issue in check_vector(bad, 2)] == ["non_finite"]
    assert [issue.code for issue in check_vector(short, 2)] == ["wrong_dimension"]


def test_duplicate_vectors_are_reported() -> None:
    items = [
        EmbeddedChunk(chunk_id="a", vector=(1.0, 0.0)),
        EmbeddedChunk(chunk_id="b", vector=(0.0, 1.0)),
        EmbeddedChunk(chunk_id="c", vector=(1.0, 0.0)),
    ]

    assert duplicate_vector_groups(items) == [["a", "c"]]
    assert norm_stats(items)["count"] == 3


def test_index_compatibility_accepts_same_space_rejects_shifted() -> None:
    stored = [[1.0, 0.0], [0.0, 1.0]]
    same = [[1.0, 0.0], [0.0, 1.0]]
    shifted = [[0.0, 1.0], [1.0, 0.0]]

    compatible, worst = verify_index_compatibility(stored, same)
    assert compatible is True and worst == 1.0
    compatible, _ = verify_index_compatibility(stored, shifted)
    assert compatible is False
    assert verify_index_compatibility([], []) == (False, 0.0)


def test_retry_recovers_flaky_provider_and_gives_up() -> None:
    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise ConnectionError("transient")
        return "ok"

    assert with_retries(flaky, attempts=3, sleep=lambda _: None) == "ok"
    assert calls["count"] == 3

    def dead():
        raise ConnectionError("down")

    try:
        with_retries(dead, attempts=2, sleep=lambda _: None)
    except ConnectionError:
        pass
    else:
        raise AssertionError("exhausted retries must raise")


def test_lexical_sparse_is_deterministic_and_normalized() -> None:
    import math

    first = lexical_sparse_vector("uang kompensasi pekerja")
    second = lexical_sparse_vector("uang kompensasi pekerja")

    assert first == second
    assert abs(math.sqrt(sum(v * v for v in first.values())) - 1.0) < 1e-9
