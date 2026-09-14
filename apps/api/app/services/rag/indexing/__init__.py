"""Indexing stage: verified writes, filters, manifests, and fences."""

from app.services.rag.indexing.filters import build_filter
from app.services.rag.indexing.governance import (
    FenceRegistry,
    build_release_manifest,
    load_verified_artifact,
    verify_release_manifest,
    write_artifact_manifest,
)
from app.services.rag.indexing.guards import (
    METADATA_LIMIT_BYTES,
    clear_namespace_guarded,
    estimate_metadata_size,
    fit_metadata,
    write_verified,
)
from app.services.rag.indexing.pinecone_backend import PineconeVectorStore
from app.services.rag.indexing.schemas import (
    NamespaceClearance,
    ReleaseManifest,
    StoredVector,
    WriteReport,
)
from app.services.rag.indexing.store import InMemoryVectorStore, VectorStore

__all__ = [
    "FenceRegistry",
    "InMemoryVectorStore",
    "METADATA_LIMIT_BYTES",
    "NamespaceClearance",
    "PineconeVectorStore",
    "ReleaseManifest",
    "StoredVector",
    "VectorStore",
    "WriteReport",
    "build_filter",
    "build_release_manifest",
    "clear_namespace_guarded",
    "estimate_metadata_size",
    "fit_metadata",
    "load_verified_artifact",
    "verify_release_manifest",
    "write_artifact_manifest",
    "write_verified",
]
