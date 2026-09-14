"""Write an accepted external BGE-M3 artifact into a verified Pinecone staging namespace.

This is deliberately separate from retrieval and release activation. A staging
namespace is never made active here; callers must complete governance and
publication in a subsequent, explicit operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services.ingestion.artifacts import ArtifactStore
from app.services.ingestion.external_embeddings import (
    DEFAULT_DIMENSIONS,
    DEFAULT_MODEL,
    DEFAULT_REVISION,
    IMPORT_SCHEMA_VERSION,
    accept_external_embeddings,
)
from app.services.ingestion.retry import (
    RetryPolicy,
    is_transient_error,
    run_with_retry,
    run_with_timeout,
)

MAX_BATCH_SIZE = 100
PINECONE_METADATA_TEXT_LIMIT = 12_000
STAGING_MANIFEST_SCHEMA_VERSION = "kerjapedia-external-staging-index-v1"


class ExternalVectorStore(Protocol):
    def clear_namespace(self) -> None: ...

    def upsert(self, vectors: list[dict[str, Any]]) -> int: ...

    def fetch_metadata(self, vector_ids: list[str]) -> dict[str, dict[str, Any]]: ...

    def namespace_vector_count(self) -> int: ...


@dataclass(frozen=True)
class StagingIndexConfig:
    batch_size: int = MAX_BATCH_SIZE
    timeout_seconds: float = 60.0
    max_retries: int = 3
    retry_initial_seconds: float = 1.0
    verification_attempts: int = 5

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= MAX_BATCH_SIZE:
            raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if self.retry_initial_seconds < 0:
            raise ValueError("retry_initial_seconds must not be negative")
        if self.verification_attempts < 1:
            raise ValueError("verification_attempts must be positive")


@dataclass(frozen=True)
class StagingIndexResult:
    schema_version: str
    status: str
    namespace: str
    expected_vector_count: int
    verified_vector_count: int
    vector_manifest_checksum: str
    source_embedding_sha256: str
    batches: int
    retries: int
    duration_seconds: float
    manifest_path: str


class ExternalStagingIndexError(RuntimeError):
    def __init__(self, message: str, *, failed_ids: Sequence[str] = ()) -> None:
        self.failed_ids = tuple(failed_ids)
        super().__init__(message)


class PineconeStagingStore:
    """Minimal write-only Pinecone adapter used only by this ingestion stage."""

    def __init__(
        self,
        *,
        api_key: str,
        index_name: str,
        namespace: str,
        dimensions: int = DEFAULT_DIMENSIONS,
        metric: str = "dotproduct",
    ) -> None:
        if not api_key:
            raise ValueError("PINECONE_API_KEY is required for staging indexing")
        self.api_key = api_key
        self.index_name = index_name
        self.namespace = namespace
        self.dimensions = dimensions
        self.metric = metric
        self._client: Any | None = None
        self._index: Any | None = None

    def clear_namespace(self) -> None:
        self._ensure_compatible_index()
        try:
            self._pinecone_index().delete(namespace=self.namespace, delete_all=True)
        except Exception as exc:
            # A never-before-used staging namespace is already empty. Pinecone
            # reports that legitimate first-run state as HTTP 404.
            if _is_namespace_not_found(exc):
                return
            raise

    def upsert(self, vectors: list[dict[str, Any]]) -> int:
        if not vectors or len(vectors) > MAX_BATCH_SIZE:
            raise ValueError(f"Pinecone batch must contain 1..{MAX_BATCH_SIZE} vectors")
        self._ensure_compatible_index()
        response = self._pinecone_index().upsert(vectors=vectors, namespace=self.namespace)
        count = getattr(response, "upserted_count", None)
        if count is None and isinstance(response, dict):
            count = response.get("upserted_count")
        if count is None:
            raise RuntimeError("Pinecone upsert response omitted upserted_count")
        return int(count)

    def fetch_metadata(self, vector_ids: list[str]) -> dict[str, dict[str, Any]]:
        response = self._pinecone_index().fetch(ids=vector_ids, namespace=self.namespace)
        vectors = getattr(response, "vectors", None)
        if vectors is None and isinstance(response, dict):
            vectors = response.get("vectors", {})
        output: dict[str, dict[str, Any]] = {}
        for vector_id, vector in dict(vectors or {}).items():
            metadata = getattr(vector, "metadata", None)
            if metadata is None and isinstance(vector, dict):
                metadata = vector.get("metadata", {})
            output[str(vector_id)] = dict(metadata or {})
        return output

    def namespace_vector_count(self) -> int:
        response = self._pinecone_index().describe_index_stats()
        namespaces = getattr(response, "namespaces", None)
        if namespaces is None and isinstance(response, dict):
            namespaces = response.get("namespaces", {})
        namespace = dict(namespaces or {}).get(self.namespace)
        if namespace is None:
            return 0
        count = getattr(namespace, "vector_count", None)
        if count is None and isinstance(namespace, dict):
            count = namespace.get("vector_count")
        if count is None:
            raise RuntimeError("Pinecone namespace statistics omitted vector_count")
        return int(count)

    def _ensure_compatible_index(self) -> None:
        client = self._pinecone_client()
        description = (
            client.indexes.describe(self.index_name)
            if hasattr(client, "indexes")
            else client.describe_index(self.index_name)
        )
        dimension = _describe_value(description, "dimension")
        metric = _describe_value(description, "metric")
        if int(dimension or 0) != self.dimensions:
            raise RuntimeError(
                f"Pinecone index dimension is {dimension}; expected {self.dimensions}"
            )
        if str(metric or "") != self.metric:
            raise RuntimeError(f"Pinecone index metric is {metric}; expected {self.metric}")

    def _pinecone_client(self) -> Any:
        if self._client is None:
            try:
                from pinecone import Pinecone
            except ImportError as exc:
                raise RuntimeError("pinecone is required for staging indexing") from exc
            self._client = Pinecone(api_key=self.api_key)
        return self._client

    def _pinecone_index(self) -> Any:
        if self._index is None:
            client = self._pinecone_client()
            self._index = (
                client.index(self.index_name)
                if hasattr(client, "index")
                else client.Index(self.index_name)
            )
        return self._index


def stage_external_embeddings(
    *,
    store: ExternalVectorStore,
    chunks_path: Path,
    embeddings_path: Path,
    colab_manifest_path: Path,
    import_receipt_path: Path,
    staging_manifest_path: Path,
    namespace: str,
    config: StagingIndexConfig | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> StagingIndexResult:
    """Clear, write, verify, and receipt an immutable external staging namespace."""
    config = config or StagingIndexConfig()
    _require_accepted_receipt(
        import_receipt_path, chunks_path, embeddings_path, colab_manifest_path
    )
    # Re-validation closes the gap between receipt creation and an index write.
    accept_external_embeddings(
        chunks_path=chunks_path,
        embeddings_path=embeddings_path,
        colab_manifest_path=colab_manifest_path,
        receipt_path=import_receipt_path,
    )
    chunks = _load_chunks(chunks_path)
    embedding_sha256 = _sha256(embeddings_path)
    expected_metadata = {
        chunk_id: _expected_metadata(chunk, embedding_sha256=embedding_sha256)
        for chunk_id, chunk in chunks.items()
    }
    if len(expected_metadata) != len(chunks):
        raise ExternalStagingIndexError("Duplicate chunk IDs in staging input")

    started = time.monotonic()
    retries = _retry_call(store.clear_namespace, config=config, sleep=sleep)
    batches = 0
    indexed = 0
    try:
        batch: list[dict[str, Any]] = []
        for record in _iter_embeddings(embeddings_path, chunks):
            batch.append(
                _pinecone_vector(
                    record,
                    chunks[record["chunk_id"]],
                    namespace,
                    embedding_sha256,
                )
            )
            if len(batch) == config.batch_size:
                retries += _write_batch(store, batch, config=config, sleep=sleep)
                indexed += len(batch)
                batches += 1
                batch = []
        if batch:
            retries += _write_batch(store, batch, config=config, sleep=sleep)
            indexed += len(batch)
            batches += 1

        _verify_vectors(store, expected_metadata, config=config, sleep=sleep)
        if indexed != len(expected_metadata):
            raise ExternalStagingIndexError(
                "Indexed count does not match expected vector count"
            )
    except Exception as exc:
        try:
            _retry_call(store.clear_namespace, config=config, sleep=sleep)
        except Exception as cleanup_exc:
            raise ExternalStagingIndexError(
                "Staging indexing failed and namespace cleanup failed: "
                f"{type(cleanup_exc).__name__}"
            ) from exc
        if isinstance(exc, ExternalStagingIndexError):
            raise
        raise ExternalStagingIndexError(f"Staging indexing failed: {type(exc).__name__}") from exc

    vector_manifest_checksum = _metadata_manifest_checksum(expected_metadata)
    result = StagingIndexResult(
        schema_version=STAGING_MANIFEST_SCHEMA_VERSION,
        status="verified",
        namespace=namespace,
        expected_vector_count=len(expected_metadata),
        verified_vector_count=len(expected_metadata),
        vector_manifest_checksum=vector_manifest_checksum,
        source_embedding_sha256=embedding_sha256,
        batches=batches,
        retries=retries,
        duration_seconds=round(time.monotonic() - started, 6),
        manifest_path=staging_manifest_path.as_posix(),
    )
    ArtifactStore(staging_manifest_path.parent).write_json(
        Path(staging_manifest_path.name),
        {**asdict(result), "expected_vector_ids": sorted(expected_metadata)},
    )
    return result


def default_namespace(embedding_sha256: str) -> str:
    return f"staging-bge-m3-{embedding_sha256[:20]}"


def _require_accepted_receipt(
    receipt_path: Path,
    chunks_path: Path,
    embeddings_path: Path,
    colab_manifest_path: Path,
) -> None:
    receipt = _load_object(receipt_path, "embedding import receipt")
    if (
        receipt.get("schema_version") != IMPORT_SCHEMA_VERSION
        or receipt.get("status") != "accepted"
    ):
        raise ExternalStagingIndexError("Embedding artifact has not been accepted")
    for key, path in (
        ("chunks_sha256", chunks_path),
        ("embeddings_sha256", embeddings_path),
        ("colab_manifest_sha256", colab_manifest_path),
    ):
        if receipt.get(key) != _sha256(path):
            raise ExternalStagingIndexError(f"Embedding import receipt is stale: {key}")


def _load_chunks(path: Path) -> dict[str, dict[str, Any]]:
    chunks: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            payload = _load_jsonl(line, path, line_number)
            chunk_id = _required_text(payload, "chunk_id", line_number)
            if chunk_id in chunks:
                raise ExternalStagingIndexError(
                    f"Duplicate canonical chunk ID: {chunk_id}"
                )
            chunks[chunk_id] = payload
    if not chunks:
        raise ExternalStagingIndexError("No canonical chunks are available")
    return chunks


def _iter_embeddings(path: Path, chunks: Mapping[str, dict[str, Any]]):
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            payload = _load_jsonl(line, path, line_number)
            chunk_id = _required_text(payload, "chunk_id", line_number)
            if chunk_id in seen or chunk_id not in chunks:
                raise ExternalStagingIndexError(
                    f"Invalid external embedding ID: {chunk_id}"
                )
            if payload.get("content_hash") != chunks[chunk_id].get("content_hash"):
                raise ExternalStagingIndexError(f"External embedding hash mismatch: {chunk_id}")
            seen.add(chunk_id)
            yield payload
    if seen != set(chunks):
        raise ExternalStagingIndexError("External embedding artifact is incomplete")


def _pinecone_vector(
    embedding: dict[str, Any],
    chunk: dict[str, Any],
    namespace: str,
    embedding_sha256: str,
) -> dict[str, Any]:
    dense = embedding.get("dense_vector")
    sparse = embedding.get("sparse_vector")
    if not isinstance(dense, list) or len(dense) != DEFAULT_DIMENSIONS:
        raise ExternalStagingIndexError(
            f"Invalid dense vector: {embedding.get('chunk_id')}"
        )
    if not isinstance(sparse, dict) or not sparse:
        raise ExternalStagingIndexError(
            f"Invalid sparse vector: {embedding.get('chunk_id')}"
        )
    try:
        dense_values = [float(value) for value in dense]
        sparse_pairs = sorted((int(key), float(value)) for key, value in sparse.items())
    except (TypeError, ValueError) as exc:
        raise ExternalStagingIndexError(
            f"Invalid vector values: {embedding.get('chunk_id')}"
        ) from exc
    if not all(math.isfinite(value) for value in dense_values) or not any(dense_values):
        raise ExternalStagingIndexError(
            f"Invalid dense vector: {embedding.get('chunk_id')}"
        )
    if any(index < 0 or not math.isfinite(value) for index, value in sparse_pairs):
        raise ExternalStagingIndexError(
            f"Invalid sparse vector: {embedding.get('chunk_id')}"
        )
    return {
        "id": embedding["chunk_id"],
        "values": dense_values,
        "sparse_values": {
            "indices": [index for index, _ in sparse_pairs],
            "values": [value for _, value in sparse_pairs],
        },
        "metadata": _vector_metadata(chunk, embedding, namespace, embedding_sha256),
    }


def _vector_metadata(
    chunk: dict[str, Any],
    embedding: dict[str, Any],
    namespace: str,
    embedding_sha256: str,
) -> dict[str, Any]:
    provenance = chunk.get("metadata") or {}
    document = provenance.get("document") or {}
    structure = provenance.get("structure") or {}
    ingestion = provenance.get("ingestion") or {}
    section = " | ".join(
        str(value) for value in (structure.get("bagian"), structure.get("paragraf")) if value
    )
    metadata = {
        "chunk_id": chunk["chunk_id"],
        "document_id": chunk["document_id"],
        "title": document.get("document_title"),
        "short_title": document.get("document_title"),
        "regulation_type": document.get("document_type"),
        "number": document.get("document_number"),
        "year": document.get("year"),
        "legal_status": document.get("regulation_status"),
        "source_name": chunk.get("source"),
        "source_url": chunk.get("source_url"),
        "file_hash": document.get("file_hash"),
        "local_file": document.get("source_file"),
        "embedding_model": embedding["model"],
        "embedding_revision": embedding["model_revision"],
        "vector_dimension": embedding["dimensions"],
        "content_hash": chunk["content_hash"],
        "embedding_artifact_sha256": embedding_sha256,
        "provenance_metadata_hash": (provenance.get("chunk") or {}).get("metadata_hash"),
        "ingestion_version": ingestion.get("ingestion_version"),
        "parser_version": ingestion.get("parser_version"),
        "chunker_version": ingestion.get("chunker_version"),
        "chapter": structure.get("bab"),
        "section": section or None,
        "article": structure.get("pasal"),
        "paragraph": structure.get("ayat"),
        "page_start": chunk.get("page_start"),
        "page_end": chunk.get("page_end"),
        "token_count": chunk.get("token_count"),
        "text": str(chunk["content"])[:PINECONE_METADATA_TEXT_LIMIT],
        "retrieval_text": str(chunk["content"])[:PINECONE_METADATA_TEXT_LIMIT],
        # Staged vectors cannot be retrieved as a published corpus.
        "publication_status": "draft",
        "source_verification_status": "pending",
        "legal_review_status": "pending",
        "is_current": False,
        "staging_namespace": namespace,
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _expected_metadata(chunk: dict[str, Any], *, embedding_sha256: str) -> dict[str, Any]:
    provenance = chunk.get("metadata") or {}
    document = provenance.get("document") or {}
    return {
        "chunk_id": chunk["chunk_id"],
        "document_id": chunk["document_id"],
        "content_hash": chunk["content_hash"],
        "file_hash": document.get("file_hash"),
        "embedding_model": DEFAULT_MODEL,
        "embedding_revision": DEFAULT_REVISION,
        "vector_dimension": DEFAULT_DIMENSIONS,
        "embedding_artifact_sha256": embedding_sha256,
    }


def _write_batch(
    store: ExternalVectorStore,
    batch: list[dict[str, Any]],
    *,
    config: StagingIndexConfig,
    sleep: Callable[[float], None],
) -> int:
    retries = _retry_call(
        lambda: _assert_upsert_count(store, batch),
        config=config,
        sleep=sleep,
    )
    return retries


def _assert_upsert_count(store: ExternalVectorStore, batch: list[dict[str, Any]]) -> None:
    count = store.upsert(batch)
    if count != len(batch):
        raise ExternalStagingIndexError("Pinecone did not acknowledge the full batch")


def _retry_call(
    call: Callable[[], None],
    *,
    config: StagingIndexConfig,
    sleep: Callable[[float], None],
) -> int:
    attempts = 1

    def on_retry(attempt: int, _delay: float, _exc: Exception) -> None:
        nonlocal attempts
        attempts = attempt + 1

    run_with_retry(
        lambda: run_with_timeout(call, config.timeout_seconds),
        policy=RetryPolicy(
            max_retries=config.max_retries,
            initial_delay_seconds=config.retry_initial_seconds,
        ),
        on_retry=on_retry,
        sleep=sleep,
    )
    return attempts - 1


def _verify_vectors(
    store: ExternalVectorStore,
    expected_metadata: Mapping[str, Mapping[str, Any]],
    *,
    config: StagingIndexConfig,
    sleep: Callable[[float], None],
) -> None:
    expected_ids = list(expected_metadata)
    for attempt in range(config.verification_attempts):
        fetched: dict[str, dict[str, Any]] = {}
        try:
            for start in range(0, len(expected_ids), config.batch_size):
                vector_ids = expected_ids[start : start + config.batch_size]
                fetched.update(
                    run_with_timeout(
                        lambda ids=vector_ids: store.fetch_metadata(ids),
                        config.timeout_seconds,
                    )
                )
            count = run_with_timeout(store.namespace_vector_count, config.timeout_seconds)
        except Exception as exc:
            if (
                attempt + 1 >= config.verification_attempts
                or not is_transient_error(exc)
            ):
                raise ExternalStagingIndexError("Staging verification request failed") from exc
            sleep(min(config.retry_initial_seconds * (2**attempt), 30.0))
            continue
        missing = sorted(set(expected_ids) - set(fetched))
        mismatched = [
            chunk_id
            for chunk_id, expected in expected_metadata.items()
            if chunk_id in fetched
            and any(fetched[chunk_id].get(key) != value for key, value in expected.items())
        ]
        if not missing and not mismatched and count == len(expected_ids):
            return
        if attempt + 1 < config.verification_attempts:
            sleep(min(config.retry_initial_seconds * (2**attempt), 30.0))
            continue
        raise ExternalStagingIndexError(
            f"Staging reconciliation failed: expected={len(expected_ids)}, indexed={count}, "
            f"missing={len(missing)}, metadata_mismatch={len(mismatched)}",
            failed_ids=[*missing, *mismatched],
        )


def _metadata_manifest_checksum(metadata: Mapping[str, Mapping[str, Any]]) -> str:
    encoded = json.dumps(
        metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _load_jsonl(line: str, path: Path, line_number: int) -> dict[str, Any]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ExternalStagingIndexError(f"Invalid JSONL at {path}:{line_number}") from exc
    if not isinstance(payload, dict):
        raise ExternalStagingIndexError(f"JSONL row must be an object at {path}:{line_number}")
    return payload


def _required_text(payload: Mapping[str, Any], key: str, line_number: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ExternalStagingIndexError(f"Missing {key} at line {line_number}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _describe_value(description: object, field: str) -> Any:
    return getattr(description, field, None) or (
        description.get(field) if isinstance(description, dict) else None
    )


def _is_namespace_not_found(exc: Exception) -> bool:
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    return status == 404 and "namespace" in str(exc).lower()


def main() -> None:
    from app.core.config import settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace")
    parser.add_argument("--index-name")
    parser.add_argument("--batch-size", type=int, default=MAX_BATCH_SIZE)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[5]
    embedding_dir = root / "storage/ingestion/embeddings/BAAI-bge-m3" / DEFAULT_REVISION
    embeddings_path = embedding_dir / "bge_m3_embeddings.jsonl"
    namespace = args.namespace or default_namespace(_sha256(embeddings_path))
    result = stage_external_embeddings(
        store=PineconeStagingStore(
            api_key=settings.pinecone_api_key or "",
            index_name=args.index_name or settings.pinecone_index_name,
            namespace=namespace,
        ),
        chunks_path=root / "storage/ingestion/preembedding/exports/chunks.jsonl",
        embeddings_path=embeddings_path,
        colab_manifest_path=embedding_dir / "bge_m3_embedding_manifest.json",
        import_receipt_path=embedding_dir / "embedding_import_manifest.json",
        staging_manifest_path=embedding_dir / "staging_index_manifest.json",
        namespace=namespace,
        config=StagingIndexConfig(batch_size=args.batch_size),
    )
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
