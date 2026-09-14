"""Chunk records with stable identities and explicit continuations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkingConfig:
    """Budgets in estimated tokens. Hard caps, not wishes."""

    target_tokens: int = 350
    max_tokens: int = 550
    overlap_sentences: int = 2
    min_merge_tokens: int = 180
    parent_tokens: int = 1200


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit. IDs are content hashes: identical rebuilds of
    the same document version yield identical IDs, so citations and
    regression baselines survive rebuilds."""

    chunk_id: str
    document_id: str
    short_title: str
    chapter: str | None = None
    section: str | None = None
    article: str | None = None
    paragraph: str | None = None
    page_start: int = 0
    page_end: int = 0
    text: str = ""
    retrieval_text: str = ""
    parent_text: str = ""
    token_estimate: int = 0
    part: int = 1
    parts: int = 1
    continued: bool = False
