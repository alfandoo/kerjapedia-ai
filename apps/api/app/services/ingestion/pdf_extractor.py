from __future__ import annotations

import math
import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import replace
from pathlib import Path

import fitz

from app.services.ingestion.schemas import ExtractedPage

KNOWN_MARGIN_LINE_RE = re.compile(
    r"^\s*(?:PRESIDEN\s+REPUBLIK\s+INDONESIA|SK\s+No\.|"
    r"www\.peraturan\.go\.id|jdih\.|-?\s*\d+\s*-?)\s*$",
    re.IGNORECASE,
)
PROTECTED_LEGAL_HEADING_RE = re.compile(
    r"^\s*(?:BAB\s+[IVXLCDM]+|Bagian\b|Paragraf\b|Pasal\s+\d+|Ayat\b)",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned.strip()


def extract_pages(
    path: Path,
    min_text_chars: int = 40,
    *,
    detect_tables: bool = True,
) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []

    with fitz.open(path) as document:
        for index, page in enumerate(document, start=1):
            raw_text = normalize_text(page.get_text("text"))
            quality_score, quality_flags = assess_text_quality(raw_text, min_text_chars)
            table_count = _detect_table_count(page) if detect_tables else 0
            if table_count:
                quality_flags.append("table_detected")
            if page.rotation:
                quality_flags.append(f"page_rotation={int(page.rotation)}")
            pages.append(
                ExtractedPage(
                    page_number=index,
                    text=raw_text,
                    text_length=len(raw_text),
                    requires_ocr=quality_score < 0.65,
                    quality_score=quality_score,
                    quality_flags=quality_flags,
                    raw_text=raw_text,
                    rotation=int(page.rotation),
                    table_count=table_count,
                )
            )

    return pages


def remove_repeated_margin_noise(
    pages: list[ExtractedPage],
    *,
    recurrence_ratio: float = 0.30,
    margin_lines: int = 3,
) -> list[ExtractedPage]:
    if not pages:
        return []
    candidates: Counter[str] = Counter()
    page_candidates: list[set[str]] = []
    for page in pages:
        lines = [line for line in page.text.splitlines() if line.strip()]
        margin = [*lines[:margin_lines], *lines[-margin_lines:]]
        signatures = {
            _margin_signature(line)
            for line in margin
            if line and not PROTECTED_LEGAL_HEADING_RE.match(line)
        }
        page_candidates.append(signatures)
        candidates.update(signatures)

    threshold = max(3, math.ceil(len(pages) * recurrence_ratio))
    repeated = {signature for signature, count in candidates.items() if count >= threshold}
    cleaned_pages: list[ExtractedPage] = []
    for page, signatures in zip(pages, page_candidates, strict=True):
        lines = [line for line in page.text.splitlines() if line.strip()]
        removed: list[str] = []
        kept: list[str] = []
        for position, line in enumerate(lines):
            in_margin = position < margin_lines or position >= max(0, len(lines) - margin_lines)
            signature = _margin_signature(line)
            known_noise = KNOWN_MARGIN_LINE_RE.match(line) is not None
            if not PROTECTED_LEGAL_HEADING_RE.match(line) and (
                in_margin and (known_noise or (signature in repeated and signature in signatures))
            ):
                removed.append(line)
            else:
                kept.append(line)
        text = "\n".join(kept).strip()
        score, flags = assess_text_quality(text)
        flags.extend(flag for flag in page.quality_flags if flag.startswith(("table_", "page_")))
        if removed:
            flags.append(f"margin_noise_removed={len(removed)}")
        cleaned_pages.append(
            replace(
                page,
                text=text,
                text_length=len(text),
                requires_ocr=score < 0.65,
                quality_score=score,
                quality_flags=flags,
                removed_margin_lines=removed,
            )
        )
    return cleaned_pages


def assess_text_quality(text: str, min_text_chars: int = 40) -> tuple[float, list[str]]:
    compact = "".join(character for character in text if not character.isspace())
    flags: list[str] = []
    if len(text) < min_text_chars:
        flags.append("insufficient_text")
    if not compact:
        return 0.0, [*flags, "empty_page"]

    readable_ratio = sum(
        unicodedata.category(character)[0] not in {"C", "Z"} for character in compact
    ) / len(compact)
    alphanumeric_ratio = sum(character.isalnum() for character in compact) / len(compact)
    replacement_ratio = compact.count("�") / len(compact)
    if readable_ratio < 0.97:
        flags.append("control_or_unreadable_characters")
    if alphanumeric_ratio < 0.55:
        flags.append("low_alphanumeric_ratio")
    if replacement_ratio > 0.005:
        flags.append("replacement_glyphs")

    length_score = min(1.0, len(text) / max(1, min_text_chars * 3))
    score = (
        (0.25 * length_score)
        + (0.35 * readable_ratio)
        + (0.35 * min(1.0, alphanumeric_ratio / 0.7))
        + (0.05 * max(0.0, 1.0 - (replacement_ratio * 20)))
    )
    if "insufficient_text" in flags:
        score = min(score, 0.6)
    if _has_missing_word_spaces(text):
        # Word-per-line extraction (no inter-word spaces): tokenizers, the
        # legal parser, and lexical scoring all break on this, yet the
        # character ratios above still score it ~1.0. Force OCR instead.
        flags.append("missing_word_spaces")
        score = min(score, 0.6)
    return round(max(0.0, min(score, 1.0)), 4), flags


def _has_missing_word_spaces(text: str) -> bool:
    """Detect extraction where line breaks replaced word spaces.

    Healthy legal pages wrap into long lines; broken extraction yields one
    short fragment per line (measured 0.85 fragment ratio on the broken
    Permenaker 6/2016 scan vs 0.27-0.45 on clean PDFs).
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 10:
        return False
    fragments = sum(1 for line in lines if len(line.split()) <= 2)
    return fragments / len(lines) > 0.6


def run_ocr(source: Path, target: Path, *, jobs: int = 2, force: bool = False) -> Path:
    try:
        import ocrmypdf
    except ImportError as exc:
        raise RuntimeError("ocrmypdf is required for scanned legal documents.") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {
        "language": ["ind", "eng"],
        # Spaceless pages already carry (broken) text: skip_text would keep it.
        "skip_text": not force,
        "force_ocr": force,
        "deskew": True,
        "rotate_pages": True,
        "optimize": 1,
        "jobs": max(1, min(jobs, 2)),
        "tesseract_timeout": 180,
        "progress_bar": False,
    }
    if shutil.which("unpaper"):
        kwargs["clean"] = True
    ocrmypdf.ocr(source, target, **kwargs)
    return target


def _margin_signature(line: str) -> str:
    normalized = " ".join(line.casefold().split())
    return re.sub(r"\d+", "#", normalized)


def _detect_table_count(page: fitz.Page) -> int:
    try:
        finder = page.find_tables()
    except (AttributeError, RuntimeError, ValueError):
        return 0
    return len(getattr(finder, "tables", []) or [])
