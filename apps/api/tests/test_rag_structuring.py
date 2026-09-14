from app.services.rag.structuring import (
    AliasTable,
    detect_marker,
    parse_segments,
    validate_segments,
)
from app.services.rag.structuring.schemas import LegalSegment


def make_page(number: int, text: str):
    from types import SimpleNamespace

    return SimpleNamespace(page_number=number, text=text)


def test_glued_markers_normalize_with_provenance() -> None:
    marker = detect_marker("Pasal5", AliasTable())

    assert marker is not None
    assert (marker.kind, marker.label, marker.provenance) == ("article", "Pasal 5", "normalized")


def test_phantom_suffix_never_becomes_article_label() -> None:
    # Glued year-suffix lines ("Pasal 4Tahun 2021 ...") read as citation
    # fragments, never as headings.
    assert detect_marker("Pasal 4Tahun 2021 tentang Pengupahan", AliasTable()) is None
    marker = detect_marker("Pasal 15A", AliasTable())
    assert marker is not None
    assert marker.label == "Pasal 15A"


def test_inserted_article_suffix_survives() -> None:
    marker = detect_marker("Pasal 15A", AliasTable())

    assert marker is not None
    assert marker.label == "Pasal 15A"


def test_reference_is_not_a_heading() -> None:
    line = "THR sebagaimana dimaksud dalam Pasal 2 ayat (1) diberikan."
    assert detect_marker(line, AliasTable()) is None


def test_inline_heading_splits_segment() -> None:
    pages = [make_page(1, "Isi ketentuan umum.\nAturan penutup. Pasal 6 Isi pasal enam.")]

    segments = parse_segments("DOC", pages)

    assert [segment.article for segment in segments] == [None, "Pasal 6"]
    assert segments[1].marker_provenance == "inline"
    assert "Isi pasal enam" in segments[1].text


def test_appendix_and_considerans_are_typed() -> None:
    pages = [
        make_page(
            1,
            "Menimbang bahwa perlu aturan.\n"
            "MEMUTUSKAN\n"
            "Pasal 1\nIsi pasal satu.\n"
            "LAMPIRAN\nDaftar tabel.",
        )
    ]

    segments = parse_segments("DOC", pages)
    by_kind = {segment.kind for segment in segments}

    assert {"considerans", "resolution", "substantive", "appendix"} <= by_kind


def test_paragraph_breaks_survive_in_segment_text() -> None:
    pages = [make_page(1, "Pasal 1\nAyat satu.\n\nAyat dua.")]

    segments = parse_segments("DOC", pages)

    assert "\n\n" in segments[0].text


def test_unstructured_fallback_never_returns_empty() -> None:
    pages = [make_page(1, "Teks tanpa struktur hukum sama sekali.")]

    segments = parse_segments("DOC", pages)

    assert len(segments) == 1
    assert segments[0].kind == "preamble"
    assert parse_segments("DOC", [make_page(1, "   ")]) == []


def test_tens_repair_restores_dropped_one() -> None:
    marker = detect_marker("Pasall0", AliasTable())

    assert marker is not None
    assert (marker.kind, marker.label) == ("article", "Pasal 10")


def test_implausible_article_number_is_content() -> None:
    assert detect_marker("Pasal 4024", AliasTable()) is None


def test_citation_line_is_not_an_opening() -> None:
    line = "Pasal 185 huruf b Undang-Undang Nomor 13 Tahun 2003"
    assert detect_marker(line, AliasTable()) is None


def test_considerans_markers_stay_content() -> None:
    pages = [
        make_page(1, "Menimbang bahwa perlu aturan.\nPasal 185 huruf b Undang-Undang Nomor 1.")
    ]

    segments = parse_segments("DOC", pages)

    assert len(segments) == 1
    assert segments[0].kind == "considerans"
    assert segments[0].article is None


def test_toc_run_markers_are_dropped_and_reported() -> None:
    from app.services.rag.structuring import parse_segments_report

    pages = [
        make_page(1, "Isi pasal empat.\nPasal6\nPasa17\nPasa18\nBABIII\nPasa19\nIsi penting."),
    ]

    segments, report = parse_segments_report("DOC", pages)

    # Run interiors drop; the tail edge (Pasa19, followed by content) still
    # opens — bounded limitation, caught downstream by article-coverage gates.
    assert report["toc_lines_dropped"] == 3
    assert [segment.article for segment in segments] == [None, "Pasal 9"]
    assert "Isi penting." in segments[-1].text
    assert "Pasa17" not in segments[-1].text


def test_page_break_heading_survives_toc_rule() -> None:
    pages = [
        make_page(1, "Isi sebelumnya.\nPasal 9"),
        make_page(2, "(1) Isi ayat pertama."),
    ]

    segments = parse_segments("DOC", pages)

    assert [segment.article for segment in segments] == [None, "Pasal 9"]


def test_bare_heading_before_bare_ayat_survives() -> None:
    pages = [make_page(1, "Pasal 9\n(1)\nIsi ayat pertama.")]

    segments = parse_segments("DOC", pages)

    assert [segment.article for segment in segments] == ["Pasal 9"]


def test_alias_table_replaces_document_hacks() -> None:
    aliases = AliasTable(substitutions=[(r"\bTHR(?=Keagamaan\b)", "THR ")])

    marker = detect_marker("THRKeagamaan adalah pendapatan.", aliases)

    assert marker is None  # no structural marker; alias only repaired spacing


def test_validation_catches_gaps_duplicates_and_phantoms() -> None:
    def segment(segment_id: str, **overrides) -> LegalSegment:
        base = {
            "segment_id": segment_id,
            "document_id": "DOC",
            "article": "Pasal 9",
            "paragraph": "Ayat (1)",
            "page_start": 1,
            "page_end": 1,
            "text": "Isi ketentuan yang cukup panjang untuk lolos batas minimum.",
            "kind": "substantive",
        }
        base.update(overrides)
        return LegalSegment(**base)

    segments = [
        segment("a", paragraph="Ayat (1)"),
        segment("b", paragraph="Ayat (1)"),
        segment("c", paragraph="Ayat (3)"),
        segment("d", article="Pasal 4Tahun", paragraph=None),
        segment("e", article="Pasal 9", paragraph=None, text="x"),
    ]

    issues = validate_segments(segments)
    by_code = {issue.code for issue in issues}

    assert {"ayat_duplicate", "ayat_gap", "bad_article_label", "too_short"} <= by_code
