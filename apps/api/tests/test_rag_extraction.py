from pathlib import Path

import fitz

from app.services.rag.extraction import (
    ExtractedPage,
    assess_quality,
    extract_pages,
    extract_tables,
    needs_ocr,
    normalize_text,
    remove_margin_noise,
    spacing_fragment_ratio,
)
from app.services.rag.extraction.extractor import _column_text


def test_normalize_folds_unicode_and_joins_wrapped_lines() -> None:
    assert normalize_text("ﬁ \u00a0test\u200b") == "fi test"
    assert normalize_text("masing-\nmasing pekerja") == "masing-masing pekerja"
    assert normalize_text("ayat berikut\nUndang-Undang baru") == "ayat berikut\nUndang-Undang baru"


def test_quality_flags_spaceless_extraction_for_ocr() -> None:
    broken = "\n".join(["Indonesia", "Tahun", "2003", "tentang"] * 8)

    assert spacing_fragment_ratio(broken) > 0.6
    score, flags = assess_quality(broken)
    assert score < 0.65
    assert "missing_word_spaces" in flags


def test_quality_keeps_healthy_paragraphs() -> None:
    healthy = (
        "Pengusaha wajib membayarkan tunjangan hari raya kepada pekerja "
        "paling lambat tujuh hari sebelum hari raya keagamaan di perusahaan."
    )

    score, flags = assess_quality(healthy)

    assert score >= 0.65
    assert "missing_word_spaces" not in flags


def test_column_reader_keeps_left_column_first() -> None:
    class FakePage:
        def get_text(self, kind: str):
            assert kind == "blocks"
            # Content-stream order: right column first (the classic trap).
            return [
                (300.0, 72.0, 500.0, 90.0, "R1 right\n", 0, 0),
                (72.0, 72.0, 250.0, 90.0, "L1 left\n", 0, 0),
                (300.0, 100.0, 500.0, 118.0, "R2 right\n", 0, 0),
                (72.0, 100.0, 250.0, 118.0, "L2 left\n", 0, 0),
            ]

    assert _column_text(FakePage()).split() == [
        "L1", "left", "L2", "left", "R1", "right", "R2", "right",
    ]


def test_two_column_pdf_uses_columns_mode(tmp_path: Path) -> None:
    pdf = tmp_path / "cols.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(350, 72, 523, 300), "R1\nR2\nR3")
    page.insert_textbox(fitz.Rect(350, 320, 523, 550), "R4\nR5\nR6")
    page.insert_textbox(fitz.Rect(72, 72, 220, 300), "L1\nL2\nL3 enough words here")
    page.insert_textbox(fitz.Rect(72, 320, 220, 550), "L4\nL5\nL6 to pass quality gates")
    document.save(pdf)
    document.close()

    pages = extract_pages(pdf)

    assert pages[0].mode == "columns"
    text = pages[0].text
    assert text.index("L1") < text.index("R1")


def test_ruling_line_table_extracts_rows(tmp_path: Path) -> None:
    pdf = tmp_path / "table.pdf"
    document = fitz.open()
    page = document.new_page()
    rect = fitz.Rect(72, 72, 300, 150)
    page.draw_rect(rect)
    page.draw_line(fitz.Point(72, 111), fitz.Point(300, 111))
    page.draw_line(fitz.Point(186, 72), fitz.Point(186, 150))
    page.insert_textbox(fitz.Rect(75, 75, 183, 108), "denda")
    page.insert_textbox(
        fitz.Rect(189, 75, 297, 108), "5 persen enough words for a sentence here"
    )
    page.insert_textbox(fitz.Rect(75, 114, 183, 147), "sanksi")
    page.insert_textbox(
        fitz.Rect(189, 114, 297, 147), "administratif berlaku untuk semua perusahaan"
    )
    document.save(pdf)
    document.close()

    pages = extract_pages(pdf)

    assert pages[0].tables, "expected the grid to be detected as a table"
    rows = pages[0].tables[0].rows
    assert any("denda" in cell for row in rows for cell in row)
    assert "tables_detected=1" in pages[0].flags


def test_margin_cleaner_removes_footers_but_keeps_spaceless_headings() -> None:
    def page(number: int, body: str) -> ExtractedPage:
        return ExtractedPage(
            page_number=number,
            text=f"KEMENTERIAN KETENAGAKERJAAN\n{body}\n- {number} -",
            raw_text="",
            kind="text",
            mode="text",
        )

    pages = [
        page(1, "Pasal 1\nKetentuan umum berlaku."),
        page(2, "Isi ketentuan kedua."),
        page(3, "Pasal5\nKetentuan kelima berlaku."),
        page(4, "Isi ketentuan keempat."),
    ]

    cleaned, removals = remove_margin_noise(pages)

    reasons = {removal.line: removal.reason for removal in removals}
    assert reasons.get("KEMENTERIAN KETENAGAKERJAAN") == "repeated_margin"
    assert reasons.get("- 3 -") == "known_pattern"
    assert all("Pasal" not in removal.line for removal in removals)
    assert any("Pasal5" in line for page in cleaned for line in page.text.splitlines())


def test_empty_page_is_classified_not_indexed_silently(tmp_path: Path) -> None:
    pdf = tmp_path / "empty.pdf"
    document = fitz.open()
    document.new_page()
    document.save(pdf)
    document.close()

    pages = extract_pages(pdf)

    assert pages[0].kind == "empty"
    assert needs_ocr(pages[0]) is False


def test_extract_tables_degrades_to_empty_without_tables() -> None:
    assert extract_tables(object(), 1) == ()
