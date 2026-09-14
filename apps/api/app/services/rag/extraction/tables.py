"""Table extraction: ruling-line tables become row data.

Tables carry the numbers the claim verifier needs (fines, amounts), so
they are extracted as structure — never left to dissolve into body text.
Detection failures degrade to zero tables, never to an exception.
"""

from __future__ import annotations

from app.services.rag.extraction.normalize import normalize_text
from app.services.rag.extraction.schemas import TableBlock


def extract_tables(page: object, page_number: int) -> tuple[TableBlock, ...]:
    """Extract ruling-line tables from a PyMuPDF page object."""
    try:
        finder = page.find_tables()  # type: ignore[union-attr]
    except (AttributeError, RuntimeError, ValueError):
        return ()
    tables = getattr(finder, "tables", None) or []
    blocks: list[TableBlock] = []
    for table in tables:
        try:
            raw_rows = table.extract() or []
        except (RuntimeError, ValueError):
            continue
        rows = tuple(
            tuple(normalize_text(str(cell or "")) for cell in row)
            for row in raw_rows
            if any(str(cell or "").strip() for cell in row)
        )
        if rows:
            blocks.append(TableBlock(page_number=page_number, rows=rows))
    return tuple(blocks)
