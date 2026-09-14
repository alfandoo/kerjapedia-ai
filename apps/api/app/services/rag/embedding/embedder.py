"""Batch embedding with per-batch checkpoints.

A 4000-chunk crash at chunk 3900 resumes at 3900 — checkpoints store
finished (id, vector, sparse) pairs on disk and skips them on rerun.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.rag.embedding.providers import EmbeddingProvider
from app.services.rag.embedding.schemas import EmbeddedChunk


def embed_indexed(
    items: list[tuple[str, str]],
    provider: EmbeddingProvider,
    *,
    batch_size: int = 16,
    checkpoint_dir: Path | None = None,
    on_batch: object = None,
) -> dict[str, EmbeddedChunk]:
    """Embed (chunk_id, text) pairs; resume finished ids from checkpoints."""
    done: dict[str, EmbeddedChunk] = {}
    if checkpoint_dir is not None:
        done = load_checkpoint(checkpoint_dir, provider)
    pending = [(chunk_id, text) for chunk_id, text in items if chunk_id not in done]
    callback = on_batch if callable(on_batch) else None
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        ids = [chunk_id for chunk_id, _ in batch]
        texts = [text for _, text in batch]
        vectors = provider.embed(texts)
        sparsities = provider.embed_sparse(texts)
        for chunk_id, vector, sparse in zip(ids, vectors, sparsities, strict=True):
            done[chunk_id] = EmbeddedChunk(
                chunk_id=chunk_id,
                vector=tuple(vector),
                sparse=dict(sparse),
                sparse_kind=provider.sparse_kind,
                model_name=provider.model_name,
                model_revision=provider.model_revision,
            )
        if checkpoint_dir is not None:
            save_checkpoint(checkpoint_dir, start // batch_size, done)
        if callback is not None:
            callback(start, len(batch))
    return done


def checkpoint_path(checkpoint_dir: Path, batch_index: int) -> Path:
    return checkpoint_dir / f"batch-{batch_index:05d}.json"


def save_checkpoint(
    checkpoint_dir: Path, batch_index: int, done: dict[str, EmbeddedChunk]
) -> None:
    """Persist finished vectors; later batches overwrite with more."""
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        chunk_id: {
            "vector": list(item.vector),
            "sparse": {str(index): value for index, value in item.sparse.items()},
            "sparse_kind": item.sparse_kind,
            "model_name": item.model_name,
            "model_revision": item.model_revision,
        }
        for chunk_id, item in done.items()
    }
    checkpoint_path(checkpoint_dir, batch_index).write_text(
        json.dumps(payload), encoding="utf-8"
    )


def load_checkpoint(
    checkpoint_dir: Path, provider: EmbeddingProvider
) -> dict[str, EmbeddedChunk]:
    """Reload finished vectors; entries from another model are ignored."""
    done: dict[str, EmbeddedChunk] = {}
    if not checkpoint_dir.exists():
        return done
    for path in sorted(checkpoint_dir.glob("batch-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for chunk_id, item in payload.items():
            if not isinstance(item, dict):
                continue
            if item.get("model_name") != provider.model_name:
                continue
            if item.get("model_revision") != provider.model_revision:
                continue
            vector = item.get("vector") or []
            sparse = {
                int(index): float(value)
                for index, value in (item.get("sparse") or {}).items()
            }
            done[chunk_id] = EmbeddedChunk(
                chunk_id=chunk_id,
                vector=tuple(vector),
                sparse=sparse,
                sparse_kind=str(item.get("sparse_kind") or "none"),
                model_name=str(item.get("model_name") or ""),
                model_revision=str(item.get("model_revision") or ""),
            )
    return done
