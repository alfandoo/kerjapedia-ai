"""Embedding records: fingerprinted vector spaces and checkpoints."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmbeddingConfig:
    """Everything that defines a vector space. Unpinned revision refuses
    to build anywhere except an explicit experiment."""

    provider: str = "bge_m3"  # bge_m3 | hash
    model_name: str = "BAAI/bge-m3"
    dimensions: int = 1024
    model_revision: str = ""
    batch_size: int = 16
    require_native_sparse: bool = False
    allow_unpinned_revision: bool = False


@dataclass(frozen=True)
class EmbeddedChunk:
    """One embedded text. ``sparse_kind`` records which sparse space the
    vector lives in — native and lexical sparsities never mix silently."""

    chunk_id: str
    vector: tuple[float, ...]
    sparse: dict[int, float] = field(default_factory=dict)
    sparse_kind: str = "none"  # native | lexical | none
    model_name: str = ""
    model_revision: str = ""


@dataclass(frozen=True)
class VectorIssue:
    """One rejected vector with its reason."""

    chunk_id: str
    code: str  # zero_vector | non_finite | wrong_dimension | duplicate_vector
    message: str = ""


def vector_space_id(config: EmbeddingConfig) -> str:
    """Fingerprint of a vector space: model@revision:dimensions."""
    return f"{config.model_name}@{config.model_revision}:{config.dimensions}"
