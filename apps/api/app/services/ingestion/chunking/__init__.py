"""Production-oriented structure-aware legal chunking."""

from app.services.ingestion.chunking.chunker import (
    StructureAwareChunker,
    chunk_legal_document,
)
from app.services.ingestion.chunking.models import (
    ChunkingConfig,
    ChunkingResult,
    ChunkStatistics,
)
from app.services.ingestion.chunking.tokenizer import (
    RegexTokenizer,
    Tokenizer,
)

__all__ = [
    "ChunkingConfig",
    "ChunkingResult",
    "ChunkStatistics",
    "RegexTokenizer",
    "StructureAwareChunker",
    "Tokenizer",
    "chunk_legal_document",
]
