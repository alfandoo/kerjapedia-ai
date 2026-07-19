from __future__ import annotations

from pathlib import Path

import fitz

from app.services.ingestion.schemas import ExtractedPage


def normalize_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned.strip()


def extract_pages(path: Path, min_text_chars: int = 40) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []

    with fitz.open(path) as document:
        for index, page in enumerate(document, start=1):
            text = normalize_text(page.get_text("text"))
            pages.append(
                ExtractedPage(
                    page_number=index,
                    text=text,
                    text_length=len(text),
                    requires_ocr=len(text) < min_text_chars,
                )
            )

    return pages
