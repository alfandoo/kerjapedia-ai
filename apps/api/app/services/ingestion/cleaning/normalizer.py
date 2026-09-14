"""Conservative, deterministic normalization for extracted legal text.

The cleaner operates only on normalized :class:`~app.services.ingestion.domain.Page`
records.  It deliberately does not interpret legal meaning: headings, legal
numbering, and terminology are retained, while mechanical extraction artifacts
are normalized with an audit trail.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace

from app.services.ingestion.domain import ExtractionDiagnostic, Page

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"[ \t]+([,.;:])")
_SPACE_AFTER_PUNCTUATION_RE = re.compile(r"([,;:])(?=[A-Za-zÀ-ÖØ-öø-ÿ])")
_SPACE_AROUND_SLASH_RE = re.compile(r"(?<=\w)[ \t]*/[ \t]*(?=\w)")
_LEGAL_MARKER_RE = re.compile(
    r"^\s*(?:"
    r"BAB\s+[IVXLCDM]+\b|"
    r"Bagian\b|Paragraf\b|Pasal\s*\d+\b|Ayat\b|"
    r"Penjelasan\b|Lampiran\b|\(\s*\d+\s*\)|"
    r"[IVXLCDM]+[.)]"
    r")",
    re.IGNORECASE,
)
_STANDALONE_LEGAL_MARKER_RE = re.compile(
    r"^\s*(?:"
    r"BAB\s+[IVXLCDM]+|Pasal\s*\d+|Ayat|\(\s*\d+\s*\)|[IVXLCDM]+[.)]"
    r")\s*$",
    re.IGNORECASE,
)
_STANDALONE_PAGE_NUMBER_RE = re.compile(r"^\s*-?\s*\d+\s*-?\s*$")


def clean_pages(
    pages: Sequence[Page],
    *,
    recurrence_ratio: float = 0.60,
    margin_lines: int = 3,
) -> list[Page]:
    """Return replacement pages with conservative, auditable ``cleaned_text``.

    Only recurring lines at the top or bottom of enough pages are treated as
    removable boilerplate.  The same input always yields the same page text,
    metadata, and diagnostics; source ``raw_text`` is never changed.
    """
    if not 0 < recurrence_ratio <= 1:
        raise ValueError("recurrence_ratio must be between 0 and 1")
    if margin_lines < 1:
        raise ValueError("margin_lines must be positive")
    if not pages:
        return []

    repeated_margins = _find_repeated_margins(
        pages,
        recurrence_ratio=recurrence_ratio,
        margin_lines=margin_lines,
    )
    return [
        _clean_page(page, repeated_margins=repeated_margins, margin_lines=margin_lines)
        for page in pages
    ]


def _clean_page(
    page: Page,
    *,
    repeated_margins: set[str],
    margin_lines: int,
) -> Page:
    normalized, character_stats = _normalize_characters(page.cleaned_text)
    lines = [_normalize_line(line) for line in normalized.splitlines()]
    retained_lines, removals = _remove_repeated_margins(
        lines,
        repeated_margins=repeated_margins,
        margin_lines=margin_lines,
    )
    cleaned_text, text_stats = _reflow_lines(retained_lines)
    changes = {
        **character_stats,
        **text_stats,
        "removed_repeated_margin_lines": len(removals),
        "removed_standalone_page_numbers": sum(
            _is_standalone_page_number(line) for line in removals
        ),
    }
    summary = {
        "schema_version": "cleaning-v1",
        "raw_characters": len(page.raw_text),
        "input_cleaned_characters": len(page.cleaned_text),
        "cleaned_characters": len(cleaned_text),
        "raw_sha256": _sha256(page.raw_text),
        "cleaned_sha256": _sha256(cleaned_text),
        "changed": cleaned_text != page.cleaned_text,
        "changes": changes,
        "removed_margin_lines": removals,
    }
    metadata = dict(page.metadata)
    metadata["cleaning"] = summary
    if removals:
        metadata["removed_margin_lines"] = [
            *list(metadata.get("removed_margin_lines", [])),
            *removals,
        ]
    diagnostic = ExtractionDiagnostic(
        code="cleaning.summary",
        message="Conservative text normalization completed without legal rewriting.",
        severity="info",
        page_number=page.page_number,
        details=summary,
    )
    return replace(
        page,
        cleaned_text=cleaned_text,
        diagnostics=(*page.diagnostics, diagnostic),
        metadata=metadata,
    )


def _find_repeated_margins(
    pages: Sequence[Page],
    *,
    recurrence_ratio: float,
    margin_lines: int,
) -> set[str]:
    candidates: Counter[str] = Counter()
    for page in pages:
        normalized, _ = _normalize_characters(page.cleaned_text)
        lines = [_normalize_line(line) for line in normalized.splitlines()]
        page_candidates = {
            _margin_signature(line)
            for position, line in enumerate(lines)
            if _is_margin_position(position, len(lines), margin_lines)
            and line
            and not _is_protected_legal_line(line)
        }
        candidates.update(page_candidates)

    threshold = max(3, math.ceil(len(pages) * recurrence_ratio))
    return {signature for signature, count in candidates.items() if count >= threshold}


def _remove_repeated_margins(
    lines: list[str],
    *,
    repeated_margins: set[str],
    margin_lines: int,
) -> tuple[list[str], list[str]]:
    retained: list[str] = []
    removals: list[str] = []
    for position, line in enumerate(lines):
        removable = (
            line
            and _is_margin_position(position, len(lines), margin_lines)
            and not _is_protected_legal_line(line)
            and _margin_signature(line) in repeated_margins
        )
        if removable:
            removals.append(line)
        else:
            retained.append(line)
    return retained, removals


def _normalize_characters(text: str) -> tuple[str, dict[str, int]]:
    nfc_text = unicodedata.normalize("NFC", text)
    zero_width_count = len(_ZERO_WIDTH_RE.findall(nfc_text))
    normalized = _ZERO_WIDTH_RE.sub("", nfc_text).replace("\xa0", " ")
    return normalized, {
        "unicode_nfc_applied": int(nfc_text != text),
        "removed_zero_width_characters": zero_width_count,
    }


def _normalize_line(line: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", line).strip()
    normalized = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", normalized)
    normalized = _SPACE_AFTER_PUNCTUATION_RE.sub(r"\1 ", normalized)
    return _SPACE_AROUND_SLASH_RE.sub("/", normalized)


def _reflow_lines(lines: list[str]) -> tuple[str, dict[str, int]]:
    output: list[str] = []
    index = 0
    wrapped_lines_joined = 0
    hard_hyphen_breaks_joined = 0
    soft_hyphens_removed = 0
    blank_lines_collapsed = 0

    while index < len(lines):
        current = lines[index]
        if not current:
            if output and output[-1] != "":
                output.append("")
            else:
                blank_lines_collapsed += 1
            index += 1
            continue

        while index + 1 < len(lines) and lines[index + 1] and _can_join_lines(
            current, lines[index + 1]
        ):
            next_line = lines[index + 1]
            if current.endswith("\u00ad"):
                current = current[:-1] + next_line
                soft_hyphens_removed += 1
            elif current.endswith(("-", "/")):
                ended_with_hyphen = current.endswith("-")
                current = current + next_line
                hard_hyphen_breaks_joined += int(ended_with_hyphen)
            else:
                current = f"{current} {next_line}"
                wrapped_lines_joined += 1
            index += 1

        soft_hyphens_removed += current.count("\u00ad")
        output.append(current.replace("\u00ad", ""))
        index += 1

    while output and not output[-1]:
        output.pop()
        blank_lines_collapsed += 1
    return "\n".join(output), {
        "joined_wrapped_lines": wrapped_lines_joined,
        "joined_hard_hyphen_breaks": hard_hyphen_breaks_joined,
        "removed_soft_hyphens": soft_hyphens_removed,
        "collapsed_blank_lines": blank_lines_collapsed,
    }


def _can_join_lines(current: str, next_line: str) -> bool:
    if _is_standalone_legal_marker(current) or _is_protected_legal_line(next_line):
        return False
    if current.endswith(("\u00ad", "-", "/")):
        return True
    if current.endswith((".", ";", ":", "?", "!")):
        return False
    if current.rstrip().endswith("Rp") and next_line[:1].isdigit():
        return True
    return next_line[:1].islower()


def _is_margin_position(position: int, line_count: int, margin_lines: int) -> bool:
    # A short page can otherwise be classified as all margin. Restrict its
    # evidence window so substantive text in the middle cannot become a
    # repeated-header candidate merely because page layouts are compact.
    edge_width = min(margin_lines, max(1, line_count // 4))
    return position < edge_width or position >= max(0, line_count - edge_width)


def _is_protected_legal_line(line: str) -> bool:
    return _LEGAL_MARKER_RE.match(line) is not None


def _is_standalone_legal_marker(line: str) -> bool:
    return _STANDALONE_LEGAL_MARKER_RE.match(line) is not None


def _is_standalone_page_number(line: str) -> bool:
    return _STANDALONE_PAGE_NUMBER_RE.match(line) is not None


def _margin_signature(line: str) -> str:
    normalized = " ".join(line.casefold().split())
    return re.sub(r"\d+", "#", normalized)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
