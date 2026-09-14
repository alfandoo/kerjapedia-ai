"""Generate resumable BGE-M3 embeddings from a KerjaPedia ``chunks.jsonl`` export.

Designed for a Google Colab GPU runtime. Upload ``chunks.jsonl`` to the
notebook session, then run:

    !pip install -q FlagEmbedding==1.4.2 huggingface-hub
    !python colab_embed_bge_m3.py --input chunks.jsonl --output bge_m3_embeddings.jsonl

The output deliberately contains vectors and stable join keys only. Keep the
original chunks file: it remains the canonical content and provenance source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

MODEL_NAME = "BAAI/bge-m3"
MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
VECTOR_DIMENSIONS = 1024
OUTPUT_SCHEMA_VERSION = "kerjapedia-bge-m3-embeddings-v1"


@dataclass(frozen=True)
class InputChunk:
    chunk_id: str
    content: str
    content_hash: str


def load_chunks(path: Path) -> list[InputChunk]:
    """Load and validate canonical chunks before allocating GPU work."""
    chunks: list[InputChunk] = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                chunk_id = _required_text(raw, "chunk_id")
                content = _required_text(raw, "content")
                content_hash = _required_text(raw, "content_hash")
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"Invalid input at line {line_number}: {exc}") from exc
            expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if content_hash != expected_hash:
                raise ValueError(f"Invalid content_hash for {chunk_id} at line {line_number}")
            if chunk_id in seen_ids:
                raise ValueError(f"Duplicate chunk_id in input: {chunk_id}")
            seen_ids.add(chunk_id)
            chunks.append(InputChunk(chunk_id, content, content_hash))
    if not chunks:
        raise ValueError("Input contains no chunks")
    return chunks


def completed_chunks(path: Path) -> dict[str, str]:
    """Return output IDs already complete for this exact model input hash."""
    if not path.exists():
        return {}
    completed: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                chunk_id = _required_text(raw, "chunk_id")
                content_hash = _required_text(raw, "content_hash")
                if raw.get("model") != MODEL_NAME or raw.get("model_revision") != MODEL_REVISION:
                    raise ValueError("model identity differs")
                vector = raw.get("dense_vector")
                if not isinstance(vector, list) or len(vector) != VECTOR_DIMENSIONS:
                    raise ValueError("invalid dense vector dimensions")
                if chunk_id in completed:
                    raise ValueError(f"duplicate chunk_id: {chunk_id}")
                completed[chunk_id] = content_hash
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"Invalid existing output at line {line_number}: {exc}") from exc
    return completed


def embed(
    chunks: list[InputChunk],
    *,
    input_path: Path,
    output_path: Path,
    failures_path: Path,
    manifest_path: Path,
    batch_size: int,
    max_retries: int,
) -> dict[str, Any]:
    """Embed missing chunks and persist a checkpoint after every successful batch."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative")

    try:
        import torch
        from FlagEmbedding import BGEM3FlagModel
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "Install dependencies first: pip install FlagEmbedding==1.4.2 huggingface-hub"
        ) from exc

    if not torch.cuda.is_available():
        raise RuntimeError("A GPU runtime is required. In Colab choose Runtime > Change runtime type > GPU.")

    existing = completed_chunks(output_path)
    missing = [chunk for chunk in chunks if existing.get(chunk.chunk_id) != chunk.content_hash]
    conflicting = [chunk_id for chunk_id, checksum in existing.items() if any(
        item.chunk_id == chunk_id and item.content_hash != checksum for item in chunks
    )]
    if conflicting:
        raise ValueError(
            "Output contains the same chunk_id with another content hash; use a new output file. "
            f"First conflict: {conflicting[0]}"
        )

    model_path = snapshot_download(repo_id=MODEL_NAME, revision=MODEL_REVISION)
    model = BGEM3FlagModel(
        model_path,
        use_fp16=True,
        batch_size=batch_size,
        passage_max_length=550,
        query_max_length=512,
    )
    started = time.monotonic()
    failed: list[dict[str, str]] = []
    written = 0
    with output_path.open("a", encoding="utf-8") as output:
        for batch in _batches(missing, batch_size):
            encoded, errors = _embed_batch_with_isolation(model, batch, max_retries)
            failed.extend(errors)
            for chunk, dense, sparse in encoded:
                _validate_dense(chunk.chunk_id, dense)
                record = {
                    "schema_version": OUTPUT_SCHEMA_VERSION,
                    "chunk_id": chunk.chunk_id,
                    "content_hash": chunk.content_hash,
                    "model": MODEL_NAME,
                    "model_revision": MODEL_REVISION,
                    "vector_space": f"{MODEL_NAME}@{MODEL_REVISION}:{VECTOR_DIMENSIONS}",
                    "dimensions": VECTOR_DIMENSIONS,
                    "dense_vector": dense,
                    "sparse_vector": sparse,
                }
                output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                written += 1
            output.flush()

    failures_path.write_text(
        json.dumps(failed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "input_path": str(input_path),
        "model": MODEL_NAME,
        "model_revision": MODEL_REVISION,
        "dimensions": VECTOR_DIMENSIONS,
        "input_chunks": len(chunks),
        "previously_completed": len(chunks) - len(missing),
        "embedded_this_run": written,
        "failed": len(failed),
        "output_path": str(output_path),
        "failures_path": str(failures_path),
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if failed:
        raise RuntimeError(f"{len(failed)} chunks failed; see {failures_path}")
    return manifest


def _embed_batch_with_isolation(
    model: Any, batch: list[InputChunk], max_retries: int
) -> tuple[list[tuple[InputChunk, list[float], dict[str, float]]], list[dict[str, str]]]:
    try:
        return _encode_batch(model, batch, max_retries), []
    except Exception as batch_error:  # isolate failures so no chunk is silently skipped
        if len(batch) == 1:
            return [], [{"chunk_id": batch[0].chunk_id, "error": str(batch_error)}]
        successes: list[tuple[InputChunk, list[float], dict[str, float]]] = []
        failures: list[dict[str, str]] = []
        for chunk in batch:
            try:
                successes.extend(_encode_batch(model, [chunk], max_retries))
            except Exception as item_error:
                failures.append({"chunk_id": chunk.chunk_id, "error": str(item_error)})
        return successes, failures


def _encode_batch(
    model: Any, batch: list[InputChunk], max_retries: int
) -> list[tuple[InputChunk, list[float], dict[str, float]]]:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            result = model.encode(
                [item.content for item in batch],
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
                batch_size=len(batch),
            )
            dense_vectors = result["dense_vecs"]
            sparse_vectors = result["lexical_weights"]
            if len(dense_vectors) != len(batch) or len(sparse_vectors) != len(batch):
                raise RuntimeError("BGE-M3 returned an incomplete batch")
            return [
                (
                    item,
                    _normalise_dense(vector),
                    {str(index): float(weight) for index, weight in sparse.items()},
                )
                for item, vector, sparse in zip(batch, dense_vectors, sparse_vectors, strict=True)
            ]
        except Exception as exc:
            last_error = exc
            if attempt == max_retries:
                break
            time.sleep(min(2**attempt, 8))
    assert last_error is not None
    raise last_error


def _normalise_dense(vector: Any) -> list[float]:
    dense = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in dense))
    if norm == 0:
        raise RuntimeError("BGE-M3 returned a zero dense vector")
    return [value / norm for value in dense]


def _validate_dense(chunk_id: str, dense: list[float]) -> None:
    if len(dense) != VECTOR_DIMENSIONS:
        raise RuntimeError(
            f"BGE-M3 returned {len(dense)} dimensions for {chunk_id}; expected {VECTOR_DIMENSIONS}"
        )


def _batches(items: list[InputChunk], size: int) -> Iterable[list[InputChunk]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _required_text(record: object, key: str) -> str:
    if not isinstance(record, dict) or not isinstance(record.get(key), str) or not record[key]:
        raise ValueError(f"{key} is required")
    return record[key]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", default=Path("bge_m3_embeddings.jsonl"), type=Path)
    parser.add_argument("--failures", default=Path("bge_m3_embedding_failures.json"), type=Path)
    parser.add_argument("--manifest", default=Path("bge_m3_embedding_manifest.json"), type=Path)
    parser.add_argument("--batch-size", default=16, type=int)
    parser.add_argument("--max-retries", default=3, type=int)
    args = parser.parse_args()
    chunks = load_chunks(args.input)
    manifest = embed(
        chunks,
        input_path=args.input,
        output_path=args.output,
        failures_path=args.failures,
        manifest_path=args.manifest,
        batch_size=args.batch_size,
        max_retries=args.max_retries,
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
