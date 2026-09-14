from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from app.services.ingestion import pdf_extractor
from app.services.ingestion.domain import Chunk, Document, LegalSection, Page
from app.services.ingestion.pdf_extractor import (
    extract_pages,
    from_legacy_extracted_page,
    parse_pdf_pages,
)
from app.services.ingestion.schemas import ExtractedPage


def _write_pdf(path: Path, page_texts: list[str], *, rotation: int = 0) -> None:
    document = fitz.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
        if rotation:
            page.set_rotation(rotation)
    document.save(path)
    document.close()


def test_normalized_models_retain_required_provenance(tmp_path: Path) -> None:
    page = Page(page_number=1, raw_text=" Pasal 1 ", cleaned_text="Pasal 1")
    document = Document(
        document_id="UU-13-2003",
        title="Undang-Undang Nomor 13 Tahun 2003",
        source="JDIH BPK",
        source_url="https://peraturan.bpk.go.id/",
        file_path=tmp_path / "uu-13-2003.pdf",
        file_hash="a" * 64,
        page_count=1,
        metadata={"regulation_type": "UU", "year": 2003},
        ingestion_version="v3",
        pages=(page,),
    )
    section = LegalSection(
        type="pasal",
        identifier="pasal-1",
        title=None,
        text="Pasal 1",
        page_start=1,
        page_end=1,
        parent="document",
        children=("ayat-1",),
    )
    chunk = Chunk(
        chunk_id="chunk-1",
        document_id=document.document_id,
        content="Pasal 1",
        page_start=1,
        page_end=1,
        legal_hierarchy={"pasal": "Pasal 1"},
        metadata={"source_url": document.source_url},
        content_hash="b" * 64,
    )

    assert document.pages == (page,)
    assert document.metadata["regulation_type"] == "UU"
    assert section.parent == "document"
    assert section.children == ("ayat-1",)
    assert chunk.legal_hierarchy == {"pasal": "Pasal 1"}
    assert chunk.content_hash == "b" * 64


def test_parse_normal_pdf_returns_normalized_page(tmp_path: Path) -> None:
    pdf = tmp_path / "normal.pdf"
    _write_pdf(pdf, ["Pasal 1   Pekerja berhak atas perlindungan."])

    pages = parse_pdf_pages(pdf)

    assert len(pages) == 1
    assert isinstance(pages[0], Page)
    assert pages[0].page_number == 1
    assert "Pasal 1" in pages[0].raw_text
    assert pages[0].cleaned_text == "Pasal 1 Pekerja berhak atas perlindungan."
    assert pages[0].metadata["extraction_failed"] is False


def test_parse_preserves_empty_page(tmp_path: Path) -> None:
    pdf = tmp_path / "empty.pdf"
    _write_pdf(pdf, [""])

    pages = parse_pdf_pages(pdf)

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].raw_text == ""
    assert pages[0].cleaned_text == ""
    assert pages[0].diagnostics[0].code == "pdf.empty_page"


def test_parse_preserves_multi_page_ordering(tmp_path: Path) -> None:
    pdf = tmp_path / "ordered.pdf"
    _write_pdf(pdf, ["Halaman pertama", "Halaman kedua", "Halaman ketiga"])

    pages = parse_pdf_pages(pdf)

    assert [page.page_number for page in pages] == [1, 2, 3]
    assert [page.cleaned_text for page in pages] == [
        "Halaman pertama",
        "Halaman kedua",
        "Halaman ketiga",
    ]


def test_page_extraction_failure_is_reported_without_dropping_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePage:
        rotation = 0

        def get_text(self, _mode: str) -> str:
            raise RuntimeError("broken content stream")

    class FakeDocument:
        page_count = 1

        def __enter__(self) -> FakeDocument:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def load_page(self, _index: int) -> FakePage:
            return FakePage()

    monkeypatch.setattr(pdf_extractor.fitz, "open", lambda _path: FakeDocument())

    pages = parse_pdf_pages(Path("broken.pdf"))

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].metadata["extraction_failed"] is True
    assert pages[0].diagnostics[0].code == "pdf.page_extraction_failed"
    assert pages[0].diagnostics[0].exception_type == "RuntimeError"


def test_parse_preserves_unicode_before_and_after_cleaning(tmp_path: Path) -> None:
    pdf = tmp_path / "unicode.pdf"
    _write_pdf(pdf, ["Pekerja café memperoleh hak."])

    page = parse_pdf_pages(pdf)[0]

    assert "café" in page.raw_text
    assert "café" in page.cleaned_text


def test_parse_records_page_metadata(tmp_path: Path) -> None:
    pdf = tmp_path / "metadata.pdf"
    _write_pdf(pdf, ["Pasal 1 mengatur hak pekerja."], rotation=90)

    page = parse_pdf_pages(pdf, detect_tables=False)[0]

    assert page.metadata["rotation"] == 90
    assert page.metadata["table_count"] == 0
    assert isinstance(page.metadata["quality_score"], float)
    assert isinstance(page.metadata["quality_flags"], list)
    assert isinstance(page.metadata["requires_ocr"], bool)


def test_legacy_page_adapter_preserves_existing_contract(tmp_path: Path) -> None:
    pdf = tmp_path / "legacy.pdf"
    _write_pdf(pdf, ["Pasal 2 berlaku untuk setiap pekerja."])

    legacy_pages = extract_pages(pdf)

    assert isinstance(legacy_pages[0], ExtractedPage)
    assert legacy_pages[0].text == "Pasal 2 berlaku untuk setiap pekerja."
    normalized = from_legacy_extracted_page(legacy_pages[0])
    assert normalized.page_number == legacy_pages[0].page_number
    assert normalized.cleaned_text == legacy_pages[0].text
    assert normalized.raw_text == legacy_pages[0].raw_text
