"""Marker detection with confidence provenance.

Markers must start the line. Glued forms (``Pasal5``) and OCR confusions
(``Pasa15``) are repaired explicitly and marked ``normalized``; mid-line
markers split the line and are marked ``inline``. Phantom suffixes
(``Pasal 4Tahun``) never become article labels: a suffix letter counts
only before a non-lowercase boundary.
"""

from __future__ import annotations

import re

from app.services.rag.structuring.schemas import AliasTable, Marker

_CHAPTER_RE = re.compile(r"^BAB\s+([IVXLCDM]+)\b", re.IGNORECASE)
_SECTION_RE = re.compile(r"^Bagian\s+(.+)$", re.IGNORECASE)
_SUBSECTION_RE = re.compile(r"^Paragraf\s+(.+)$", re.IGNORECASE)
_PARAGRAPH_RE = re.compile(r"^\(([0-9]+)\)\s*(.*)$")
_LETTER_RE = re.compile(r"^([A-Za-z])\.\s+(.+)$")
_CONSIDERANS_RE = re.compile(r"^(Menimbang|Mengingat)\b", re.IGNORECASE)
_RESOLUTION_RE = re.compile(r"^(MEMUTUSKAN|Menetapkan)\b")
_APPENDIX_RE = re.compile(r"^LAMPIRAN\b", re.IGNORECASE)
_EXPLANATION_RE = re.compile(r"^PENJELASAN\b", re.IGNORECASE)

# Glued/OCR marker repairs, longest first. The "tens" pattern restores the
# dropped "1": "Pasall0" (letter-L + zero) means "Pasal 10".
_GLUED_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bPasa[l1i][l1i]([0-9]+[A-Z]?)\b", re.IGNORECASE), "Pasal 1\\1"),
    (re.compile(r"\bPasa[1i]([0-9]+[A-Z]?)\b", re.IGNORECASE), "Pasal \\1"),
    (re.compile(r"\bPasal([0-9]+[A-Z]?)\b"), "Pasal \\1"),
)
_ARTICLE_HEAD_RE = re.compile(r"^Pasal\s+(\d+)([A-Z])?(?![a-z])")
_ARTICLE_INLINE_RE = re.compile(r"Pasal\s+(\d+)([A-Z])?(?![a-z])")


def apply_aliases(line: str, aliases: AliasTable) -> str:
    """Document-specific substitutions; the default table is empty."""
    for pattern, replacement in aliases.substitutions:
        line = re.sub(pattern, replacement, line)
    return line


def normalize_marker_line(line: str, aliases: AliasTable) -> tuple[str, bool]:
    """Collapse whitespace, apply aliases, repair glued/OCR markers.

    Returns the normalized line plus whether it was changed.
    """
    collapsed = " ".join(line.split())
    aliased = apply_aliases(collapsed, aliases)
    repaired = aliased
    for pattern, replacement in _GLUED_PATTERNS:
        repaired = pattern.sub(replacement, repaired)
    chapter_match = re.match(r"^BAB([IVXLCDM]+)\b", repaired, re.IGNORECASE)
    if chapter_match:
        repaired = f"BAB {chapter_match.group(1).upper()}{repaired[chapter_match.end():]}"
    return repaired, repaired != collapsed


def detect_marker(line: str, aliases: AliasTable) -> Marker | None:
    """Detect a structural marker at the start of a normalized line."""
    normalized, changed = normalize_marker_line(line, aliases)
    if not normalized:
        return None
    provenance = "normalized" if changed else "standalone"
    if _APPENDIX_RE.match(normalized):
        return Marker("appendix", "LAMPIRAN", "", provenance, line)
    if _EXPLANATION_RE.match(normalized):
        return Marker("explanation", "PENJELASAN", "", provenance, line)
    if match := _CHAPTER_RE.match(normalized):
        label = f"BAB {match.group(1).upper()}"
        trailing = normalized[match.end():].strip()
        return Marker("chapter", label, trailing, provenance, line)
    if match := _SECTION_RE.match(normalized):
        return Marker("section", f"Bagian {match.group(1).strip()}", "", provenance, line)
    if match := _SUBSECTION_RE.match(normalized):
        return Marker("subsection", f"Paragraf {match.group(1).strip()}", "", provenance, line)
    if match := _ARTICLE_HEAD_RE.match(normalized):
        number, suffix = match.group(1), match.group(2) or ""
        if int(number) > _MAX_PLAUSIBLE_ARTICLE:
            return None
        label = f"Pasal {number}{suffix.upper()}"
        trailing = normalized[match.end():].strip(" .:")
        if trailing and _CITATION_AFTER_MARKER_RE.search(trailing):
            # "Pasal 185 huruf b Undang-Undang Nomor ..." cites another
            # law: a reference line, never an article opening.
            return None
        return Marker("article", label, trailing, provenance, line)
    if match := _PARAGRAPH_RE.match(normalized):
        label = f"Ayat ({match.group(1)})"
        return Marker("paragraph", label, match.group(2).strip(), provenance, line)
    if match := _LETTER_RE.match(normalized):
        return Marker("letter", match.group(1).lower(), match.group(2).strip(), provenance, line)
    if _CONSIDERANS_RE.match(normalized):
        return Marker("considerans", normalized.split()[0], normalized, provenance, line)
    if _RESOLUTION_RE.match(normalized):
        return Marker("resolution", normalized.split()[0].upper(), normalized, provenance, line)
    inline = _detect_inline_article(normalized, line, changed)
    if inline is not None:
        return inline
    return None


_REFERENCE_PREPOSITIONS = frozenset(
    "dalam pada di ke dari dengan tentang menurut sesuai berdasarkan "
    "sebagaimana untuk atas oleh sebagai".split()
)
_CITATION_AFTER_MARKER_RE = re.compile(
    r"Undang-Undang|Peraturan|Nomor\s+\d|Tahun\s+\d{4}|dimaksud dalam|sebagaimana",
    re.IGNORECASE,
)
_MAX_PLAUSIBLE_ARTICLE = 999


def _detect_inline_article(normalized: str, raw: str, changed: bool) -> Marker | None:
    """An article heading glued to the previous sentence splits the segment.

    References (``dalam Pasal 2``) are not headings: an inline marker only
    counts after sentence-final punctuation and a non-preposition word.
    """
    for match in _ARTICLE_INLINE_RE.finditer(normalized):
        if match.start() == 0:
            continue
        before = normalized[: match.start()].rstrip()
        if len(before) < 10 or before[-1] not in ".?!":
            continue
        previous_word = before[:-1].split()[-1].lower() if before[:-1].split() else ""
        if previous_word in _REFERENCE_PREPOSITIONS:
            continue
        number, suffix = match.group(1), match.group(2) or ""
        if int(number) > _MAX_PLAUSIBLE_ARTICLE:
            continue
        label = f"Pasal {number}{suffix.upper()}"
        trailing = normalized[match.end():].strip(" .:")
        if trailing and _CITATION_AFTER_MARKER_RE.search(trailing):
            continue
        provenance = "normalized" if changed else "inline"
        return Marker("article", label, trailing, provenance, raw)
    return None
