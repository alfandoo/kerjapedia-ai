"""Configuration and result records for structure-aware chunking."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.ingestion.domain import Chunk


@dataclass(frozen=True)
class ChunkingConfig:
    """Token budgets for legal chunks; ``max_tokens`` is a hard limit."""

    target_tokens: int = 350
    max_tokens: int = 550
    min_tokens: int = 80
    overlap_tokens: int = 24

    def __post_init__(self) -> None:
        if self.min_tokens < 1:
            raise ValueError("min_tokens must be positive")
        if not self.min_tokens <= self.target_tokens <= self.max_tokens:
            raise ValueError("expected min_tokens <= target_tokens <= max_tokens")
        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens must not be negative")
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be smaller than target_tokens")


@dataclass(frozen=True)
class ChunkStatistics:
    number_of_chunks: int
    min_tokens: int
    max_tokens: int
    mean_tokens: float
    median_tokens: float
    p95_tokens: float
    p99_tokens: float


@dataclass(frozen=True)
class ChunkingResult:
    chunks: tuple[Chunk, ...]
    statistics: ChunkStatistics
