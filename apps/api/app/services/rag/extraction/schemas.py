"""Page records for the extraction stage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TableBlock:
    """One detected table: rows of normalized cell texts."""

    page_number: int
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class ExtractedPage:
    """A page plus how it was read. ``kind`` drives downstream strategy:
    text pages parse normally, scanned pages queue for OCR, empty pages
    are reported instead of silently indexed."""

    page_number: int
    text: str
    raw_text: str
    kind: str  # text | scanned | empty
    mode: str  # text | columns
    quality_score: float = 1.0
    flags: tuple[str, ...] = ()
    rotation: int = 0
    tables: tuple[TableBlock, ...] = ()
    spacing_fragment_ratio: float = 0.0


@dataclass(frozen=True)
class LineRemoval:
    """One discarded margin line plus why — removals stay auditable."""

    page_number: int
    line: str
    reason: str  # known_pattern | repeated_margin
