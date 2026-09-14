"""Page extraction with per-page mode selection.

- ``text`` mode: default PyMuPDF reading order.
- ``columns`` mode: side-by-side columns are read left column first
  (default order follows the content stream, which often interleaves).
- ``kind`` classifies the page for downstream strategy: ``text`` parses
  normally, ``scanned`` queues for OCR, ``empty`` is reported.
"""

from __future__ import annotations

from pathlib import Path

from app.services.rag.extraction.normalize import normalize_text
from app.services.rag.extraction.quality import (
    OCR_THRESHOLD,
    assess_quality,
    spacing_fragment_ratio,
)
from app.services.rag.extraction.schemas import ExtractedPage
from app.services.rag.extraction.tables import extract_tables

_MIN_COLUMN_BLOCKS = 2
_FULL_WIDTH_RATIO = 0.7
_MIN_BAND_SPAN_RATIO = 0.4
_MIN_BAND_OVERLAP_RATIO = 0.5


def extract_pages(path: Path, min_text_chars: int = 40) -> list[ExtractedPage]:
    """Extract every page of a PDF with mode and kind per page."""
    import fitz

    pages: list[ExtractedPage] = []
    with fitz.open(path) as document:
        for index, page in enumerate(document, start=1):
            raw = normalize_text(page.get_text("text"))
            if _has_side_by_side_columns(page):
                raw = normalize_text(_column_text(page))
                mode = "columns"
            else:
                mode = "text"
            score, flags = assess_quality(raw, min_text_chars)
            tables = extract_tables(page, index)
            if tables:
                flags.append(f"tables_detected={len(tables)}")
            if page.rotation:
                flags.append(f"page_rotation={int(page.rotation)}")
            kind = _classify_kind(page, raw, min_text_chars)
            pages.append(
                ExtractedPage(
                    page_number=index,
                    text=raw,
                    raw_text=raw,
                    kind=kind,
                    mode=mode,
                    quality_score=score,
                    flags=tuple(flags),
                    rotation=int(page.rotation),
                    tables=tables,
                    spacing_fragment_ratio=round(spacing_fragment_ratio(raw), 4),
                )
            )
    return pages


def needs_ocr(page: ExtractedPage) -> bool:
    """Scanned and low-quality text pages must go through OCR.

    Empty pages are reported, not OCR'd — there is nothing to recover.
    """
    if page.kind == "empty":
        return False
    return page.quality_score < OCR_THRESHOLD or page.kind == "scanned"


def _classify_kind(page: object, text: str, min_text_chars: int) -> str:
    if len(text.strip()) >= min_text_chars:
        return "text"
    try:
        images = page.get_images(full=True)  # type: ignore[union-attr]
    except (AttributeError, RuntimeError, ValueError):
        images = []
    if images:
        return "scanned"
    return "empty"


def _bands(blocks: list[tuple], gap: float) -> list[list[tuple]]:
    """Group blocks into x-bands (columns) by left-edge proximity."""
    bands: list[list[tuple]] = []
    for block in sorted(blocks, key=lambda item: item[0]):
        for band in bands:
            if abs(block[0] - band[0][0]) < gap:
                band.append(block)
                break
        else:
            bands.append([block])
    return bands


def _content_blocks(page: object) -> list[tuple]:
    get_text = getattr(page, "get_text", None)
    if not callable(get_text):
        return []
    try:
        blocks = get_text("blocks") or []
    except (AttributeError, RuntimeError, ValueError):
        return []
    return [block for block in blocks if str(block[4]).strip()]


def _page_width(page: object) -> float:
    rect = getattr(page, "rect", None)
    width = getattr(rect, "width", 0) if rect is not None else 0
    try:
        return float(width) or 595.0
    except (TypeError, ValueError):
        return 595.0


def _has_side_by_side_columns(page: object) -> bool:
    """True only for unambiguous wide-gutter layouts.

    Hanging indents (~30pt) and full-width title blocks must never
    trigger a reorder: a wrongly reordered page is worse than an
    uninterleaved one, so the bar is deliberately high.
    """
    width = _page_width(page)
    gap = max(100.0, 0.18 * width)
    blocks = _content_blocks(page)
    # Full-width blocks (titles, rules) veto reordering outright.
    if any(block[2] - block[0] > _FULL_WIDTH_RATIO * width for block in blocks):
        return False
    bands = [band for band in _bands(blocks, gap) if len(band) >= _MIN_COLUMN_BLOCKS]
    if len(bands) < 2:
        return False
    content_top = min(block[1] for block in blocks)
    content_bottom = max(block[3] for block in blocks)
    content_span = max(1.0, content_bottom - content_top)
    spans = []
    for band in bands[:2]:
        top = min(block[1] for block in band)
        bottom = max(block[3] for block in band)
        if (bottom - top) / content_span < _MIN_BAND_SPAN_RATIO:
            return False
        spans.append((top, bottom))
    overlap = min(spans[0][1], spans[1][1]) - max(spans[0][0], spans[1][0])
    smaller = min(spans[0][1] - spans[0][0], spans[1][1] - spans[1][0])
    return overlap / max(1.0, smaller) >= _MIN_BAND_OVERLAP_RATIO


def _column_text(page: object) -> str:
    """Read left column top-to-bottom, then the next column."""
    gap = max(100.0, 0.18 * _page_width(page))
    columns = _bands(_content_blocks(page), gap)
    ordered = [block for column in columns for block in sorted(column, key=lambda item: item[1])]
    return "\n".join(str(block[4]).strip() for block in ordered if str(block[4]).strip())
