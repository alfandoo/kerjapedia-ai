"""Line state machine: legal lines into hierarchical segments.

Each segment keeps its legal path (chapter/section/article/paragraph),
page span, kind, and the provenance of the marker that opened it.
"""

from __future__ import annotations

from typing import Protocol

from app.services.rag.structuring.markers import AliasTable, Marker, detect_marker
from app.services.rag.structuring.schemas import LegalSegment

_TOC_SKIPPABLE = frozenset({"article"})
_TOC_NEXT = frozenset({"article", "chapter", "section", "subsection"})


def _is_toc_run_entry(
    entries: list[tuple[int, str, Marker | None]], index: int
) -> bool:
    """A bare article marker followed by another bare article-or-higher
    marker is a table-of-contents/footer run, not an opening: real articles
    are always followed by their ayat or content, never directly by another
    article. Paragraph markers never trigger the skip, so page-break
    headings ("Pasal 9" + "(1) ...") survive. Skipping loses nothing — an
    empty flush is a no-op — but keeps phantom article states out."""
    _, _, marker = entries[index]
    if marker is None or marker.kind not in _TOC_SKIPPABLE or marker.trailing:
        return False
    for _, next_line, next_marker in entries[index + 1 :]:
        if not next_line:
            continue
        return (
            next_marker is not None
            and next_marker.kind in _TOC_NEXT
            and not next_marker.trailing
        )
    return False


class PageText(Protocol):
    """Anything with a page number and text (old or new page records)."""

    page_number: int
    text: str


def parse_segments(
    document_id: str,
    pages: list[PageText],
    aliases: AliasTable | None = None,
) -> list[LegalSegment]:
    """Parse pages into segments, preserving paragraph breaks in text."""
    segments, _ = parse_segments_report(document_id, pages, aliases)
    return segments


def parse_segments_report(
    document_id: str,
    pages: list[PageText],
    aliases: AliasTable | None = None,
) -> tuple[list[LegalSegment], dict[str, object]]:
    """Parse pages; the report counts dropped TOC lines and marker kinds."""
    table = aliases or AliasTable()
    builder = _Builder(document_id)
    entries: list[tuple[int, str, Marker | None]] = []
    for page in pages:
        for raw_line in page.text.splitlines():
            if not raw_line.strip():
                entries.append((page.page_number, "", None))
                continue
            entries.append(
                (page.page_number, raw_line.strip(), detect_marker(raw_line, table))
            )
    index = 0
    while index < len(entries):
        page_number, line, marker = entries[index]
        if not line:
            builder.blank(page_number)
            index += 1
            continue
        if _is_toc_run_entry(entries, index):
            builder.drop_toc_line()
            index += 1
            continue
        builder.line(page_number, line, marker)
        index += 1
    builder.flush()
    segments = builder.segments
    if segments:
        return segments, builder.report()
    fallback = [
        LegalSegment(
            segment_id=f"{document_id}-page-{page.page_number:05d}",
            document_id=document_id,
            page_start=page.page_number,
            page_end=page.page_number,
            text=page.text,
            kind="unstructured",
        )
        for page in pages
        if page.text.strip()
    ]
    return fallback, builder.report()


class _Builder:
    def __init__(self, document_id: str) -> None:
        self._document_id = document_id
        self.segments: list[LegalSegment] = []
        self._toc_dropped = 0
        self._marker_counts: dict[str, int] = {}
        self._counter = 1
        self._chapter: str | None = None
        self._section: str | None = None
        self._subsection: str | None = None
        self._article: str | None = None
        self._paragraph: str | None = None
        self._paragraph_base: str | None = None
        self._kind = "preamble"
        self._provenance = "none"
        self._buffer: list[str] = []
        self._page_start: int | None = None
        self._page_end: int | None = None

    def drop_toc_line(self) -> None:
        """Discard a table-of-contents/footer marker run member."""
        self._toc_dropped += 1

    def report(self) -> dict[str, object]:
        return {"toc_lines_dropped": self._toc_dropped, "markers": dict(self._marker_counts)}

    def blank(self, page_number: int) -> None:
        if self._buffer and self._buffer[-1] != "":
            self._buffer.append("")
            self._page_end = page_number

    def line(self, page_number: int, line: str, marker: Marker | None) -> None:
        if marker is None:
            self._append(page_number, line)
            return
        self._marker_counts[marker.kind] = self._marker_counts.get(marker.kind, 0) + 1
        if marker.kind in {"article", "paragraph", "letter"} and self._kind == "considerans":
            # Menimbang/Mengingat blocks only ever *cite* articles of other
            # laws ("Pasal 185 huruf b Undang-Undang Nomor ..."): references,
            # never openings. Keep them as content.
            self._append(page_number, line)
            return
        if marker.kind in {"appendix", "explanation", "considerans", "resolution"}:
            self.flush()
            self._kind = marker.kind
            if marker.kind == "appendix":
                self._chapter = "LAMPIRAN"
            elif marker.kind == "explanation":
                self._chapter = "PENJELASAN"
            self._section = self._subsection = None
            self._article = self._paragraph = self._paragraph_base = None
            self._provenance = marker.provenance
            self._append(page_number, line)
            return
        if marker.kind == "chapter":
            self.flush()
            self._chapter = marker.label
            self._section = self._subsection = None
            self._paragraph = self._paragraph_base = None
            self._provenance = marker.provenance
            return
        if marker.kind == "section":
            self.flush()
            self._section = marker.label
            self._subsection = None
            self._paragraph = self._paragraph_base = None
            self._provenance = marker.provenance
            if marker.trailing:
                self._append(page_number, marker.trailing)
            return
        if marker.kind == "subsection":
            self.flush()
            self._subsection = marker.label
            self._paragraph = self._paragraph_base = None
            self._provenance = marker.provenance
            return
        if marker.kind == "article":
            self.flush()
            self._article = marker.label
            self._paragraph = self._paragraph_base = None
            if self._kind in {"preamble", "considerans", "resolution"}:
                # Body openers yield to the first article; appendix and
                # explanation keep their kind for their own articles.
                self._kind = "substantive"
            self._provenance = marker.provenance
            if marker.trailing:
                self._append(page_number, marker.trailing)
            return
        if marker.kind == "paragraph" and self._article:
            self.flush()
            self._paragraph_base = marker.label
            self._paragraph = marker.label
            self._provenance = marker.provenance
            if marker.trailing:
                self._append(page_number, marker.trailing)
            return
        if marker.kind == "letter" and self._article and self._paragraph_base:
            self.flush()
            self._paragraph = f"{self._paragraph_base}, Huruf {marker.label}"
            self._provenance = marker.provenance
            if marker.trailing:
                self._append(page_number, marker.trailing)
            return
        self._append(page_number, line)

    def _append(self, page_number: int, line: str) -> None:
        if self._page_start is None:
            self._page_start = page_number
        self._page_end = page_number
        self._buffer.append(line)

    def flush(self) -> None:
        if not self._buffer or self._page_start is None or self._page_end is None:
            return
        text = "\n".join(self._buffer).strip()
        if not text:
            return
        section = " / ".join(
            value for value in (self._section, self._subsection) if value
        ) or None
        self.segments.append(
            LegalSegment(
                segment_id=f"{self._document_id}-seg-{self._counter:05d}",
                document_id=self._document_id,
                chapter=self._chapter,
                section=section,
                article=self._article,
                paragraph=self._paragraph,
                page_start=self._page_start,
                page_end=self._page_end,
                text=text,
                kind=self._kind,
                marker_provenance=self._provenance,
            )
        )
        self._counter += 1
        self._buffer = []
        self._page_start = None
        self._page_end = None
