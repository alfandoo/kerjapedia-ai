from __future__ import annotations

import hashlib
import math
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.services.ingestion.retry import (
    RetryPolicy,
    is_transient_error,
    run_with_retry,
    run_with_timeout,
)
from app.services.ingestion.schemas import DocumentMetadata, EmbeddedChunk

MAX_VECTOR_BATCH_SIZE = 100


class VectorWriteStore(Protocol):
    def clear_namespace(self) -> None: ...

    def upsert_document(
        self,
        document: DocumentMetadata,
        version: int,
        embedded_chunks: list[EmbeddedChunk],
        batch_size: int = 100,
        publication_status: str = "draft",
        source_verification_status: str | None = None,
        legal_review_status: str = "pending",
        is_current: bool = True,
        replace_document: bool = True,
        ingestion_timestamp: str | None = None,
        ingestion_stage_durations: dict[str, float] | None = None,
    ) -> int: ...

    def fetch_vector_metadata(self, vector_ids: list[str]) -> dict[str, dict]: ...

    def namespace_vector_count(self) -> int: ...


@dataclass(frozen=True)
class VectorIndexConfig:
    batch_size: int = 100
    timeout_seconds: float = 60.0
    max_retries: int = 3
    retry_initial_seconds: float = 1.0
    verification_attempts: int = 5

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= MAX_VECTOR_BATCH_SIZE:
            raise ValueError(
                f"vector batch_size must be between 1 and {MAX_VECTOR_BATCH_SIZE}"
            )
        if self.timeout_seconds <= 0:
            raise ValueError("vector timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("vector max_retries must not be negative")
        if self.retry_initial_seconds < 0:
            raise ValueError("vector retry_initial_seconds must not be negative")
        if self.verification_attempts < 1:
            raise ValueError("vector verification_attempts must be positive")


@dataclass(frozen=True)
class VectorIndexStatistics:
    expected_chunks: int
    indexed_chunks: int
    batches: int
    retries: int
    duration_seconds: float


class VectorIndexingError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failed_item_ids: Sequence[str] = (),
        cause: Exception | None = None,
    ) -> None:
        self.failed_item_ids = tuple(failed_item_ids)
        self.cause_type = type(cause).__name__ if cause is not None else None
        super().__init__(message)


def clear_namespace_reliably(
    store: VectorWriteStore,
    *,
    config: VectorIndexConfig,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Clear a staging namespace with bounded retries; return retry count."""
    attempts = 1

    def on_retry(attempt: int, _delay: float, _exc: Exception) -> None:
        nonlocal attempts
        attempts = attempt + 1

    try:
        run_with_retry(
            lambda: run_with_timeout(store.clear_namespace, config.timeout_seconds),
            policy=RetryPolicy(
                max_retries=config.max_retries,
                initial_delay_seconds=config.retry_initial_seconds,
            ),
            on_retry=on_retry,
            sleep=sleep,
        )
    except Exception as exc:
        raise VectorIndexingError(
            f"Unable to clear vector staging namespace after {attempts} attempt(s)",
            cause=exc,
        ) from exc
    return attempts - 1


def validate_chunks_for_index(
    document: DocumentMetadata,
    embedded_chunks: Sequence[EmbeddedChunk],
    *,
    expected_model: str,
    expected_revision: str,
    expected_dimension: int,
) -> None:
    """Validate vector payloads and their retrieval provenance before any write."""
    if not embedded_chunks:
        raise VectorIndexingError("No chunks were supplied for vector indexing")
    if len(document.sha256) != 64:
        raise VectorIndexingError("Document source hash is not a full SHA-256 digest")

    chunk_ids = [item.chunk.chunk_id for item in embedded_chunks]
    duplicates = sorted(
        chunk_id for chunk_id, count in Counter(chunk_ids).items() if count > 1
    )
    if duplicates:
        raise VectorIndexingError(
            "Duplicate chunk IDs were supplied for vector indexing",
            failed_item_ids=duplicates,
        )

    for item in embedded_chunks:
        chunk = item.chunk
        if (
            not chunk.chunk_id
            or chunk.document_id != document.document_id
            or chunk.source_url != document.source_url
            or not chunk.build_id
            or chunk.page_start < 1
            or chunk.page_end < chunk.page_start
            or not chunk.text.strip()
        ):
            raise VectorIndexingError(
                f"Chunk metadata is invalid for {chunk.chunk_id or '<missing>'}",
                failed_item_ids=[chunk.chunk_id or "<missing>"],
            )
        retrieval_text = chunk.retrieval_text or chunk.text
        expected_text_hash = hashlib.sha256(retrieval_text.encode("utf-8")).hexdigest()
        expected_artifact_hash = hashlib.sha256(
            f"{chunk.chunk_id}\n{retrieval_text}".encode()
        ).hexdigest()
        if (
            item.retrieval_text_sha256 != expected_text_hash
            or chunk.artifact_checksum != expected_artifact_hash
        ):
            raise VectorIndexingError(
                f"Chunk content provenance is invalid for {chunk.chunk_id}",
                failed_item_ids=[chunk.chunk_id],
            )
        if (
            item.embedding_model != expected_model
            or item.embedding_revision != expected_revision
        ):
            raise VectorIndexingError(
                f"Embedding model provenance is invalid for {chunk.chunk_id}",
                failed_item_ids=[chunk.chunk_id],
            )
        if (
            len(item.embedding) != expected_dimension
            or any(not math.isfinite(float(value)) for value in item.embedding)
            or not any(float(value) != 0.0 for value in item.embedding)
            or not item.sparse_embedding
            or any(
                int(index) < 0 or not math.isfinite(float(value))
                for index, value in item.sparse_embedding.items()
            )
        ):
            raise VectorIndexingError(
                f"Embedding vector is invalid for {chunk.chunk_id}",
                failed_item_ids=[chunk.chunk_id],
            )


def index_document_reliably(
    store: VectorWriteStore,
    document: DocumentMetadata,
    version: int,
    embedded_chunks: Sequence[EmbeddedChunk],
    *,
    expected_model: str,
    expected_revision: str,
    expected_dimension: int,
    config: VectorIndexConfig,
    publication_status: str,
    source_verification_status: str,
    legal_review_status: str,
    is_current: bool,
    sleep: Callable[[float], None] = time.sleep,
    ingestion_timestamp: str | None = None,
    ingestion_stage_durations: dict[str, float] | None = None,
) -> VectorIndexStatistics:
    validate_chunks_for_index(
        document,
        embedded_chunks,
        expected_model=expected_model,
        expected_revision=expected_revision,
        expected_dimension=expected_dimension,
    )
    started = time.monotonic()
    indexed = 0
    batches = 0
    retries = 0
    policy = RetryPolicy(
        max_retries=config.max_retries,
        initial_delay_seconds=config.retry_initial_seconds,
    )

    for start in range(0, len(embedded_chunks), config.batch_size):
        batch = list(embedded_chunks[start : start + config.batch_size])
        batch_ids = [item.chunk.chunk_id for item in batch]
        attempts = 1

        def on_retry(attempt: int, _delay: float, _exc: Exception) -> None:
            nonlocal attempts
            attempts = attempt + 1

        def write_batch(items: list[EmbeddedChunk] = batch) -> int:
            return run_with_timeout(
                lambda: store.upsert_document(
                    document,
                    version,
                    items,
                    batch_size=len(items),
                    publication_status=publication_status,
                    source_verification_status=source_verification_status,
                    legal_review_status=legal_review_status,
                    is_current=is_current,
                    replace_document=False,
                    ingestion_timestamp=ingestion_timestamp,
                    ingestion_stage_durations=ingestion_stage_durations,
                ),
                config.timeout_seconds,
            )

        try:
            count = run_with_retry(
                write_batch,
                policy=policy,
                on_retry=on_retry,
                sleep=sleep,
            )
        except Exception as exc:
            raise VectorIndexingError(
                f"Vector write failed for {len(batch_ids)} chunk(s) after "
                f"{attempts} attempt(s)",
                failed_item_ids=batch_ids,
                cause=exc,
            ) from exc
        if count != len(batch):
            raise VectorIndexingError(
                f"Vector store acknowledged {count} of {len(batch)} chunk(s)",
                failed_item_ids=batch_ids,
            )
        indexed += count
        batches += 1
        retries += attempts - 1

    return VectorIndexStatistics(
        expected_chunks=len(embedded_chunks),
        indexed_chunks=indexed,
        batches=batches,
        retries=retries,
        duration_seconds=round(time.monotonic() - started, 6),
    )


def verify_indexed_vectors(
    store: VectorWriteStore,
    expected_metadata: Mapping[str, Mapping[str, object]],
    *,
    config: VectorIndexConfig,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Reconcile exact vector IDs, count, and immutable provenance after writes."""
    expected_ids = tuple(expected_metadata)
    if not expected_ids or len(expected_ids) != len(set(expected_ids)):
        raise VectorIndexingError("Expected vector manifest is empty or duplicated")

    last_missing: list[str] = list(expected_ids)
    last_mismatched: list[str] = []
    last_count = 0
    for attempt in range(config.verification_attempts):
        try:
            fetched: dict[str, dict] = {}
            for start in range(0, len(expected_ids), config.batch_size):
                batch_ids = list(expected_ids[start : start + config.batch_size])
                response = run_with_timeout(
                    lambda ids=batch_ids: store.fetch_vector_metadata(ids),
                    config.timeout_seconds,
                )
                fetched.update(response)
            last_count = run_with_timeout(
                store.namespace_vector_count,
                config.timeout_seconds,
            )
        except Exception as exc:
            if attempt + 1 >= config.verification_attempts or not is_transient_error(exc):
                raise VectorIndexingError(
                    "Vector index verification request failed",
                    failed_item_ids=expected_ids,
                    cause=exc,
                ) from exc
            sleep(
                min(config.retry_initial_seconds * (2**attempt), 30.0)
            )
            continue

        last_missing = sorted(set(expected_ids) - set(fetched))
        last_mismatched = sorted(
            vector_id
            for vector_id, expected in expected_metadata.items()
            if vector_id in fetched
            and any(fetched[vector_id].get(key) != value for key, value in expected.items())
        )
        if (
            not last_missing
            and not last_mismatched
            and last_count == len(expected_ids)
        ):
            return
        if attempt + 1 < config.verification_attempts:
            sleep(min(config.retry_initial_seconds * (2**attempt), 30.0))

    failed_ids = sorted(set(last_missing).union(last_mismatched))
    raise VectorIndexingError(
        "Vector index reconciliation failed: "
        f"expected={len(expected_ids)}, indexed={last_count}, "
        f"missing={len(last_missing)}, metadata_mismatch={len(last_mismatched)}",
        failed_item_ids=failed_ids,
    )


def expected_vector_metadata(
    document: DocumentMetadata,
    item: EmbeddedChunk,
) -> dict[str, object]:
    retrieval_text = item.chunk.retrieval_text or item.chunk.text
    return {
        "chunk_id": item.chunk.chunk_id,
        "document_id": document.document_id,
        "build_id": item.chunk.build_id,
        "embedding_model": item.embedding_model,
        "embedding_revision": item.embedding_revision,
        "file_hash": document.sha256,
        "content_hash": hashlib.sha256(retrieval_text.encode("utf-8")).hexdigest(),
    }
