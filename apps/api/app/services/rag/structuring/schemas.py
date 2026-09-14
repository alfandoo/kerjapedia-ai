"""Structure records: segments with marker provenance and issues."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Marker:
    """One detected structural marker at a line start."""

    kind: str  # chapter | section | subsection | article | paragraph | letter
    label: str  # normalized, e.g. "Pasal 5", "Ayat (1)"
    trailing: str  # rest of the line after the marker (may hold content)
    provenance: str  # standalone | inline | normalized
    raw: str  # the line as seen before normalization


@dataclass(frozen=True)
class LegalSegment:
    """A structural unit with its legal path and page span."""

    segment_id: str
    document_id: str
    chapter: str | None = None
    section: str | None = None
    article: str | None = None
    paragraph: str | None = None
    page_start: int = 0
    page_end: int = 0
    text: str = ""
    kind: str = "substantive"
    # preamble | substantive | considerans | resolution | appendix |
    # explanation | unstructured
    marker_provenance: str = "none"


@dataclass(frozen=True)
class SegmentIssue:
    """A structural anomaly. Never silently accepted."""

    segment_id: str
    code: str  # ayat_gap | ayat_duplicate | too_short | bad_article_label
    message: str


@dataclass(frozen=True)
class AliasTable:
    """Document-specific substitutions, kept out of the generic parser."""

    substitutions: tuple[tuple[str, str], ...] = ()
