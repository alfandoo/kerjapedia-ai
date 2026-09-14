from __future__ import annotations

import logging
import math
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter
from dataclasses import replace
from pathlib import Path

import fitz

from app.services.ingestion.domain import ExtractionDiagnostic, Page
from app.services.ingestion.schemas import ExtractedPage

logger = logging.getLogger(__name__)

KNOWN_MARGIN_LINE_RE = re.compile(
    r"^\s*(?:PRESIDEN\s+REPUBLIK\s+INDONESIA|SK\s+No\.|"
    r"www\.peraturan\.go\.id|jdih\.|-?\s*\d+\s*-?)\s*$",
    re.IGNORECASE,
)
PROTECTED_LEGAL_HEADING_RE = re.compile(
    r"^\s*(?:BAB\s*[IVXLCDM]+|Bagian\b|Paragraf\b|Pasa[lI1]\s*\d+|Ayat\b|\(\s*\d+\s*\))",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned.strip()


def parse_pdf_pages(
    path: Path,
    min_text_chars: int = 40,
    *,
    detect_tables: bool = True,
) -> list[Page]:
    """Parse every PDF page into the normalized page model.

    Page-level failures become diagnostics on an empty page record so callers
    can account for every source page. Errors that prevent opening the document
    still propagate because no reliable page inventory exists in that case.
    """
    pages: list[Page] = []

    with fitz.open(path) as document:
        for index in range(document.page_count):
            page_number = index + 1
            try:
                pdf_page = document.load_page(index)
                raw_text = pdf_page.get_text("text")
                # PDF content-stream order need not match visual reading order.
                # Keep the original untouched and order the working text spatially.
                cleaned_text = normalize_text(pdf_page.get_text("text", sort=True))
                quality_score, quality_flags = assess_text_quality(
                    cleaned_text,
                    min_text_chars,
                )
                table_count = _detect_table_count(pdf_page) if detect_tables else 0
                if table_count:
                    quality_flags.append("table_detected")
                rotation = int(pdf_page.rotation)
                if rotation:
                    quality_flags.append(f"page_rotation={rotation}")

                diagnostics: tuple[ExtractionDiagnostic, ...] = ()
                if not cleaned_text:
                    diagnostics = (
                        ExtractionDiagnostic(
                            code="pdf.empty_page",
                            message="The page contains no extractable text.",
                            page_number=page_number,
                        ),
                    )
                pages.append(
                    Page(
                        page_number=page_number,
                        raw_text=raw_text,
                        cleaned_text=cleaned_text,
                        diagnostics=diagnostics,
                        metadata={
                            "extraction_failed": False,
                            "quality_score": quality_score,
                            "quality_flags": quality_flags,
                            "requires_ocr": quality_score < 0.65,
                            "rotation": rotation,
                            "table_count": table_count,
                            "removed_margin_lines": [],
                            "disposition": None,
                        },
                    )
                )
            except Exception as exc:
                pages.append(_failed_page(page_number, exc))

    return pages


def extract_pages(
    path: Path,
    min_text_chars: int = 40,
    *,
    detect_tables: bool = True,
) -> list[ExtractedPage]:
    """Return the legacy page schema for existing ingestion consumers.

    New parser integrations should call :func:`parse_pdf_pages`. This adapter
    remains while the legal parser, quality report, and stored v2 artifacts use
    ``ExtractedPage``.
    """
    return [
        to_legacy_extracted_page(page)
        for page in parse_pdf_pages(
            path,
            min_text_chars=min_text_chars,
            detect_tables=detect_tables,
        )
    ]


def to_legacy_extracted_page(page: Page) -> ExtractedPage:
    """Adapt a normalized page to the active v2 ingestion schema."""
    metadata = page.metadata
    quality_flags = list(metadata.get("quality_flags", []))
    quality_flags.extend(
        diagnostic.code for diagnostic in page.diagnostics if diagnostic.code not in quality_flags
    )
    return ExtractedPage(
        page_number=page.page_number,
        text=page.cleaned_text,
        text_length=len(page.cleaned_text),
        requires_ocr=bool(metadata.get("requires_ocr", not page.cleaned_text)),
        quality_score=float(metadata.get("quality_score", 0.0)),
        quality_flags=quality_flags,
        raw_text=page.raw_text,
        rotation=int(metadata.get("rotation", 0)),
        table_count=int(metadata.get("table_count", 0)),
        removed_margin_lines=list(metadata.get("removed_margin_lines", [])),
        disposition=metadata.get("disposition"),
    )


def from_legacy_extracted_page(page: ExtractedPage) -> Page:
    """Adapt an existing v2 page to the normalized internal model."""
    diagnostics = tuple(
        ExtractionDiagnostic(
            code=flag,
            message=f"Legacy extraction flag: {flag}",
            page_number=page.page_number,
        )
        for flag in page.quality_flags
    )
    return Page(
        page_number=page.page_number,
        raw_text=page.raw_text if page.raw_text is not None else page.text,
        cleaned_text=page.text,
        diagnostics=diagnostics,
        metadata={
            "extraction_failed": "pdf.page_extraction_failed" in page.quality_flags,
            "quality_score": page.quality_score,
            "quality_flags": list(page.quality_flags),
            "requires_ocr": page.requires_ocr,
            "rotation": page.rotation,
            "table_count": page.table_count,
            "removed_margin_lines": list(page.removed_margin_lines),
            "disposition": page.disposition,
        },
    )


def _failed_page(page_number: int, exc: Exception) -> Page:
    diagnostic = ExtractionDiagnostic(
        code="pdf.page_extraction_failed",
        message="The page could not be extracted and requires review.",
        severity="error",
        page_number=page_number,
        exception_type=type(exc).__name__,
    )
    return Page(
        page_number=page_number,
        raw_text="",
        cleaned_text="",
        diagnostics=(diagnostic,),
        metadata={
            "extraction_failed": True,
            "quality_score": 0.0,
            "quality_flags": [diagnostic.code],
            "requires_ocr": True,
            "rotation": 0,
            "table_count": 0,
            "removed_margin_lines": [],
            "disposition": None,
        },
    )


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
        flags.extend(
            flag
            for flag in page.quality_flags
            if flag.startswith(("table_", "page_", "ocr_", "pdf."))
        )
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
    # Explanations legitimately consist mostly of short legal labels and
    # 'Cukup jelas.' responses. These are not broken word spacing.
    label = re.compile(
        r"^(?:Pasal\s+\S+|Ayat\s*\(.+\)|Huruf\s+\S+|Angka\s+\S+|"
        r"BAB\s+[IVXLCDM]+|\(\d+\)|Cukup\s+jelas\.?|Dihapus\.?|[-\d .]+)$",
        re.I,
    )
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not label.fullmatch(line.strip())
    ]
    if len(lines) < 10:
        return False
    fragments = sum(1 for line in lines if len(line.split()) <= 2)
    return fragments / len(lines) > 0.6


def run_ocr(source: Path, target: Path, *, jobs: int = 2, force: bool = False) -> Path:
    # OCRmyPDF can spend several minutes rasterizing a document before it
    # reports these missing executables. Fail fast so the page-level fallback
    # can provide useful diagnostics and text instead of leaving a hung job.
    missing_dependencies = [
        name
        for name, commands in {
            "qpdf": ("qpdf",),
            "ghostscript": ("gs", "gswin64c", "gswin32c"),
        }.items()
        if not any(shutil.which(command) for command in commands)
    ]
    if missing_dependencies:
        raise RuntimeError("OCRmyPDF prerequisites unavailable: " + ", ".join(missing_dependencies))
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


def apply_page_ocr_fallback(
    source: Path,
    pages: list[ExtractedPage],
    *,
    page_numbers: list[int],
    min_text_chars: int = 40,
) -> list[ExtractedPage]:
    """OCR only deficient pages when OCRmyPDF cannot construct a PDF.

    OCRmyPDF depends on qpdf and Ghostscript.  Its absence must not turn a
    scanned regulation into an apparently successful one-page ingestion. This
    PyMuPDF/Tesseract fallback preserves the original page inventory and adds
    explicit per-page diagnostics; pages that still cannot be read remain
    marked as requiring review.
    """
    wanted = set(page_numbers)
    if not wanted:
        return pages
    replacements = {page.page_number: page for page in pages}
    language = _available_ocr_language()
    if language is None:
        return [
            _with_ocr_failure(page, "Tesseract language data is unavailable.")
            if page.page_number in wanted
            else page
            for page in pages
        ]
    try:
        with fitz.open(source) as pdf:
            for page_number in sorted(wanted):
                existing = replacements.get(page_number)
                if existing is None or page_number > pdf.page_count:
                    continue
                try:
                    pdf_page = pdf.load_page(page_number - 1)
                    ocr_text = _ocr_page_with_tesseract(pdf_page, language)
                    score, flags = assess_text_quality(ocr_text, min_text_chars)
                    flags.extend(["ocr_page_fallback", f"ocr_language={language}"])
                    replacements[page_number] = ExtractedPage(
                        page_number=page_number,
                        text=ocr_text,
                        text_length=len(ocr_text),
                        requires_ocr=score < 0.65,
                        quality_score=score,
                        quality_flags=flags,
                        raw_text=existing.raw_text,
                        rotation=existing.rotation,
                        table_count=existing.table_count,
                        removed_margin_lines=list(existing.removed_margin_lines),
                        disposition="ocr_extracted" if ocr_text and score >= 0.65 else None,
                    )
                except Exception as exc:
                    replacements[page_number] = _with_ocr_failure(existing, str(exc))
    except Exception:
        return [
            _with_ocr_failure(page, "The source PDF could not be opened for page OCR.")
            if page.page_number in wanted
            else page
            for page in pages
        ]
    return [replacements[page.page_number] for page in pages]


def _available_ocr_language() -> str | None:
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    languages = set(result.stdout.splitlines()[1:])
    if "ind" in languages and "eng" in languages:
        return "ind+eng"
    if "ind" in languages:
        return "ind"
    return "eng" if "eng" in languages else None


def _ocr_page_with_tesseract(page: fitz.Page, language: str) -> str:
    """Render one page and OCR it in a bounded subprocess.

    PyMuPDF's in-process OCR cannot be interrupted safely when Tesseract gets
    stuck on a malformed scan. A subprocess gives every page a hard timeout
    and keeps the remaining source pages available for diagnostics.
    """
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    with tempfile.TemporaryDirectory(prefix="kerjapedia-ocr-") as temporary:
        image_path = Path(temporary) / "page.png"
        image_path.write_bytes(pixmap.tobytes("png"))
        result = subprocess.run(
            ["tesseract", str(image_path), "stdout", "-l", language, "--psm", "6"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or "Tesseract failed.").strip())
        return normalize_text(result.stdout)


def _with_ocr_failure(page: ExtractedPage, message: str) -> ExtractedPage:
    logger.error("OCR failed for page %s: %s", page.page_number, message)
    return replace(
        page,
        requires_ocr=True,
        quality_flags=[
            *page.quality_flags,
            "ocr_page_fallback_failed",
            f"ocr_error={message[:500]}",
        ],
        disposition=None,
    )


def _margin_signature(line: str) -> str:
    normalized = " ".join(line.casefold().split())
    return re.sub(r"\d+", "#", normalized)


def _detect_table_count(page: fitz.Page) -> int:
    try:
        finder = page.find_tables()
    except (AttributeError, RuntimeError, ValueError):
        return 0
    return len(getattr(finder, "tables", []) or [])
