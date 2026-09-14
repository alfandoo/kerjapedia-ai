"""Page extraction: modes, kinds, tables, and cleaning."""

from app.services.rag.extraction.cleaning import (
    LineRemoval,
    remove_margin_noise,
)
from app.services.rag.extraction.extractor import extract_pages, needs_ocr
from app.services.rag.extraction.normalize import normalize_text
from app.services.rag.extraction.quality import (
    OCR_THRESHOLD,
    assess_quality,
    spacing_fragment_ratio,
)
from app.services.rag.extraction.schemas import ExtractedPage, TableBlock
from app.services.rag.extraction.tables import extract_tables

__all__ = [
    "ExtractedPage",
    "LineRemoval",
    "OCR_THRESHOLD",
    "TableBlock",
    "assess_quality",
    "extract_pages",
    "extract_tables",
    "needs_ocr",
    "normalize_text",
    "remove_margin_noise",
    "spacing_fragment_ratio",
]
