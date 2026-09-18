"""Dense and sparse embeddings with provenance and quality gates."""

from app.services.rag.embedding.embedder import (
    checkpoint_path,
    embed_indexed,
    load_checkpoint,
    save_checkpoint,
)
from app.services.rag.embedding.providers import (
    EmbeddingProvider,
    HashEmbeddingProvider,
    effective_config,
    lexical_sparse_vector,
)
from app.services.rag.embedding.quality import (
    check_vector,
    duplicate_vector_groups,
    norm_stats,
    verify_index_compatibility,
    with_retries,
)
from app.services.rag.embedding.schemas import (
    EmbeddedChunk,
    EmbeddingConfig,
    VectorIssue,
    vector_space_id,
)

__all__ = [
    "EmbeddedChunk",
    "EmbeddingConfig",
    "EmbeddingProvider",
    "HashEmbeddingProvider",
    "VectorIssue",
    "check_vector",
    "checkpoint_path",
    "duplicate_vector_groups",
    "effective_config",
    "embed_indexed",
    "lexical_sparse_vector",
    "load_checkpoint",
    "norm_stats",
    "save_checkpoint",
    "vector_space_id",
    "verify_index_compatibility",
    "with_retries",
]
