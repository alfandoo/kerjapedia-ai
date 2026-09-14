from __future__ import annotations

from app.services.ingestion.cleaning import clean_pages
from app.services.ingestion.domain import Page


def _page(page_number: int, text: str, *, raw_text: str | None = None) -> Page:
    return Page(
        page_number=page_number,
        raw_text=raw_text if raw_text is not None else text,
        cleaned_text=text,
        metadata={"source": "fixture"},
    )


def test_cleaning_preserves_indonesian_legal_markers_and_terms() -> None:
    page = _page(
        1,
        "BAB II\nPasal 15\n(1)  Pekerja / buruh  PKWT berhak atas Rp\n"
        "1.000 ,00.\nUndang-\nUndang ini berlaku.",
    )

    cleaned = clean_pages([page])[0]

    assert cleaned.cleaned_text == (
        "BAB II\nPasal 15\n(1) Pekerja/buruh PKWT berhak atas Rp 1.000,00.\n"
        "Undang-Undang ini berlaku."
    )
    assert cleaned.raw_text == page.raw_text
    assert cleaned.metadata["cleaning"]["changes"]["joined_hard_hyphen_breaks"] == 1


def test_cleaning_reflows_only_safe_wrapped_body_text() -> None:
    page = _page(
        1,
        "Pasal 15\n(1)\nSetiap pekerja\nberhak memperoleh perlindungan.\n"
        "BAB III\nKETENAGAKERJAAN",
    )

    cleaned = clean_pages([page])[0]

    assert cleaned.cleaned_text == (
        "Pasal 15\n(1)\nSetiap pekerja berhak memperoleh perlindungan.\n"
        "BAB III\nKETENAGAKERJAAN"
    )


def test_cleaning_normalizes_unicode_whitespace_blank_lines_and_soft_hyphens() -> None:
    page = _page(
        1,
        "Pasal\u00a015  \n\n\n(1)  Pengusaha wajib mematuhi per\u00adaturan.\u200b",
        raw_text="Pasal\u00a015  \n\n\n(1)  Pengusaha wajib mematuhi per\u00adaturan.\u200b",
    )

    cleaned = clean_pages([page])[0]

    assert cleaned.cleaned_text == "Pasal 15\n\n(1) Pengusaha wajib mematuhi peraturan."
    assert cleaned.metadata["cleaning"]["changes"]["removed_zero_width_characters"] == 1
    assert cleaned.metadata["cleaning"]["changes"]["removed_soft_hyphens"] == 1


def test_repeated_headers_footers_and_page_numbers_require_cross_page_evidence() -> None:
    pages = [
        _page(
            number,
            "PRESIDEN REPUBLIK INDONESIA\n"
            f"Ketentuan substantif halaman {number}.\n"
            f"- {number} -",
        )
        for number in range(1, 5)
    ]

    cleaned = clean_pages(pages)

    assert [page.cleaned_text for page in cleaned] == [
        f"Ketentuan substantif halaman {number}." for number in range(1, 5)
    ]
    assert all(
        page.metadata["cleaning"]["changes"]["removed_standalone_page_numbers"] == 1
        for page in cleaned
    )


def test_single_page_header_is_not_removed_without_repetition_evidence() -> None:
    page = _page(1, "KEMENTERIAN KETENAGAKERJAAN\nPasal 1\nKetentuan ini berlaku.")

    cleaned = clean_pages([page])[0]

    assert "KEMENTERIAN KETENAGAKERJAAN" in cleaned.cleaned_text


def test_repeated_legal_headings_are_never_treated_as_boilerplate() -> None:
    pages = [
        _page(number, f"BAB II\nPasal 15\nKetentuan halaman {number}.")
        for number in range(1, 5)
    ]

    cleaned = clean_pages(pages)

    assert all(page.cleaned_text.startswith("BAB II\nPasal 15") for page in cleaned)


def test_cleaning_diagnostics_compare_raw_and_cleaned_text() -> None:
    page = _page(1, "Pasal 1  mengatur  PKWT.", raw_text="Pasal 1   mengatur  PKWT.")

    cleaned = clean_pages([page])[0]

    diagnostic = cleaned.diagnostics[-1]
    assert diagnostic.code == "cleaning.summary"
    assert diagnostic.page_number == 1
    assert diagnostic.details["raw_sha256"] != diagnostic.details["cleaned_sha256"]
    assert diagnostic.details["raw_characters"] == len(page.raw_text)
    assert diagnostic.details["cleaned_characters"] == len(cleaned.cleaned_text)


def test_cleaning_is_deterministic_and_preserves_page_order() -> None:
    pages = [
        _page(2, "Ketentuan\nberikutnya."),
        _page(1, "Ketentuan\npertama."),
    ]

    first = clean_pages(pages)
    second = clean_pages(pages)

    assert [page.page_number for page in first] == [2, 1]
    assert first == second
