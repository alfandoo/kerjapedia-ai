from __future__ import annotations

import re

from app.services.ingestion.schemas import ExtractedPage, LegalSegment

CHAPTER_RE = re.compile(r"^BAB\s+([IVXLCDM]+[A-Z]?)\b", re.IGNORECASE)
SECTION_RE = re.compile(r"^Bagian\s+(.+)$", re.IGNORECASE)
SUBSECTION_RE = re.compile(r"^Paragraf\s+(.+)$", re.IGNORECASE)
ARTICLE_RE = re.compile(r"^Pasal\s+([0-9]+[A-Z]?)\s*[.:]?\s*$", re.IGNORECASE)
PARAGRAPH_RE = re.compile(r"^\(?([0-9]+)\)\s+(.+)$")
LETTER_RE = re.compile(r"^([a-z])\.\s+(.+)$", re.IGNORECASE)
APPENDIX_RE = re.compile(r"^LAMPIRAN\b", re.IGNORECASE)
EXPLANATION_RE = re.compile(r"^PENJELASAN\b", re.IGNORECASE)
COMPACT_CHAPTER_RE = re.compile(r"^BAB([IVXLCDM]+[A-Z]?)\b", re.IGNORECASE)
OCR_ARTICLE_TEN_PLUS_RE = re.compile(r"\bPasa[l1i][l1i]([0-9]+[A-Z]?)\b", re.IGNORECASE)
OCR_ARTICLE_RE = re.compile(r"\bPasa[1i]([0-9]+[A-Z]?)\b", re.IGNORECASE)
COMPACT_ARTICLE_RE = re.compile(r"\bPasal([0-9]+[A-Z]?)\b", re.IGNORECASE)
THR_COMPACT_RE = re.compile(r"\bTHR(?=Keagamaan\b)", re.IGNORECASE)


def normalize_legal_line(line: str) -> str:
    """Normalize common legal-heading and OCR artifacts without rewriting prose."""
    normalized = " ".join(line.split()).strip()
    normalized = THR_COMPACT_RE.sub("THR ", normalized)
    normalized = OCR_ARTICLE_TEN_PLUS_RE.sub(
        lambda match: f"Pasal 1{match.group(1)}",
        normalized,
    )
    normalized = OCR_ARTICLE_RE.sub(
        lambda match: f"Pasal {match.group(1)}",
        normalized,
    )
    normalized = COMPACT_ARTICLE_RE.sub(
        lambda match: f"Pasal {match.group(1)}",
        normalized,
    )
    if match := COMPACT_CHAPTER_RE.match(normalized):
        return f"BAB {match.group(1).upper()}{normalized[match.end() :]}"
    return normalized


def parse_legal_segments(document_id: str, pages: list[ExtractedPage]) -> list[LegalSegment]:
    segments: list[LegalSegment] = []
    chapter: str | None = None
    section: str | None = None
    subsection: str | None = None
    current_article: str | None = None
    current_paragraph: str | None = None
    paragraph_base: str | None = None
    segment_type = "preamble"
    buffer: list[str] = []
    page_start: int | None = None
    page_end: int | None = None
    counter = 1

    def flush() -> None:
        nonlocal buffer, page_start, page_end, counter
        if not buffer or page_start is None or page_end is None:
            return
        text = "\n".join(buffer).strip()
        if not text:
            return
        segments.append(
            LegalSegment(
                segment_id=f"{document_id}-seg-{counter:05d}",
                document_id=document_id,
                chapter=chapter,
                section=" / ".join(value for value in (section, subsection) if value) or None,
                article=current_article,
                paragraph=current_paragraph,
                page_start=page_start,
                page_end=page_end,
                text=text,
                segment_type=segment_type,
            )
        )
        counter += 1
        buffer = []
        page_start = None
        page_end = None

    for page in pages:
        for raw_line in page.text.splitlines():
            line = normalize_legal_line(raw_line)
            if not line:
                continue

            chapter_match = CHAPTER_RE.match(line)
            section_match = SECTION_RE.match(line)
            subsection_match = SUBSECTION_RE.match(line)
            article_match = ARTICLE_RE.match(line)
            paragraph_match = PARAGRAPH_RE.match(line)
            letter_match = LETTER_RE.match(line)

            if APPENDIX_RE.match(line):
                flush()
                segment_type = "appendix"
                chapter = "LAMPIRAN"
                section = None
                subsection = None
                current_article = None
                current_paragraph = None
                paragraph_base = None
                continue
            if EXPLANATION_RE.match(line):
                flush()
                segment_type = "explanation"
                chapter = "PENJELASAN"
                section = None
                subsection = None
                current_article = None
                current_paragraph = None
                paragraph_base = None
                continue
            if chapter_match:
                flush()
                chapter = f"BAB {chapter_match.group(1).upper()}"
                section = None
                subsection = None
                current_paragraph = None
                paragraph_base = None
                continue
            if section_match:
                flush()
                section = f"Bagian {section_match.group(1).strip()}"
                subsection = None
                current_paragraph = None
                paragraph_base = None
                continue
            if subsection_match:
                flush()
                subsection = f"Paragraf {subsection_match.group(1).strip()}"
                current_paragraph = None
                paragraph_base = None
                continue
            if article_match:
                flush()
                current_article = f"Pasal {article_match.group(1).upper()}"
                current_paragraph = None
                paragraph_base = None
                if segment_type == "preamble":
                    segment_type = "substantive"
                continue
            if paragraph_match and current_article:
                flush()
                paragraph_base = f"Ayat ({paragraph_match.group(1)})"
                current_paragraph = paragraph_base
            elif letter_match and current_article and paragraph_base:
                flush()
                current_paragraph = f"{paragraph_base}, Huruf {letter_match.group(1).lower()}"

            if page_start is None:
                page_start = page.page_number
            page_end = page.page_number
            buffer.append(line)

    flush()

    if segments:
        return segments

    return [
        LegalSegment(
            segment_id=f"{document_id}-page-{page.page_number:05d}",
            document_id=document_id,
            chapter=None,
            section=None,
            article=None,
            paragraph=None,
            page_start=page.page_number,
            page_end=page.page_number,
            text=page.text,
            segment_type="unstructured",
        )
        for page in pages
        if page.text
    ]
