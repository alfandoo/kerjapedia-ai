"""Margin/header/footer cleaning with auditable removals.

Same recurrence idea as the legacy cleaner, but every discarded line
returns a :class:`LineRemoval` with its reason, and legal headings are
protected whether or not the extractor left spaces around the number
(``Pasal5`` survives as well as ``Pasal 5``).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import replace

from app.services.rag.extraction.schemas import ExtractedPage, LineRemoval

KNOWN_MARGIN_LINE_RE = re.compile(
    r"^\s*(?:PRESIDEN\s+REPUBLIK\s+INDONESIA|SK\s+No\.|"
    r"www\.peraturan\.go\.id|jdih\.|-?\s*\d+\s*-?)\s*$",
    re.IGNORECASE,
)
PROTECTED_HEADING_RE = re.compile(
    r"^\s*(?:BAB\s+[IVXLCDM]+|Bagian\b|Paragraf\b|Pasal\s*\d+|Ayat\b)",
    re.IGNORECASE,
)


def remove_margin_noise(
    pages: list[ExtractedPage],
    *,
    margin_lines: int = 3,
    recurrence_ratio: float = 0.30,
) -> tuple[list[ExtractedPage], list[LineRemoval]]:
    """Strip repeated edge lines; return cleaned pages plus removals."""
    if not pages:
        return [], []
    page_margins: list[list[str]] = []
    candidates: Counter[str] = Counter()
    for page in pages:
        lines = [line for line in page.text.splitlines() if line.strip()]
        margin = [*lines[:margin_lines], *lines[-margin_lines:]]
        signatures = {
            _signature(line)
            for line in margin
            if line and not PROTECTED_HEADING_RE.match(line)
        }
        page_margins.append(margin)
        candidates.update(signatures)

    threshold = max(3, math.ceil(len(pages) * recurrence_ratio))
    repeated = {sig for sig, count in candidates.items() if count >= threshold}

    cleaned: list[ExtractedPage] = []
    removals: list[LineRemoval] = []
    for page in pages:
        lines = [line for line in page.text.splitlines() if line.strip()]
        kept: list[str] = []
        for position, line in enumerate(lines):
            in_margin = position < margin_lines or position >= max(0, len(lines) - margin_lines)
            if PROTECTED_HEADING_RE.match(line) or not in_margin:
                kept.append(line)
                continue
            if KNOWN_MARGIN_LINE_RE.match(line):
                removals.append(LineRemoval(page.page_number, line, "known_pattern"))
                continue
            if _signature(line) in repeated:
                removals.append(LineRemoval(page.page_number, line, "repeated_margin"))
                continue
            kept.append(line)
        cleaned.append(replace(page, text="\n".join(kept).strip()))
    return cleaned, removals


def _signature(line: str) -> str:
    normalized = " ".join(line.casefold().split())
    return re.sub(r"\d+", "#", normalized)
