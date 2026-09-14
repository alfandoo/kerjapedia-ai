from __future__ import annotations

import pytest

from app.services.ingestion.domain import LegalSection, Page
from app.services.ingestion.structure import parse_legal_sections


def _page(number: int, text: str) -> Page:
    return Page(page_number=number, raw_text=text, cleaned_text=text)


def _section(
    sections: list[LegalSection],
    section_type: str,
    identifier: str,
) -> LegalSection:
    return next(
        section
        for section in sections
        if section.type == section_type and section.identifier == identifier
    )


def test_simple_pp_detects_preamble_decision_chapter_article_and_ayat() -> None:
    pages = [
        _page(
            1,
            "PERATURAN PEMERINTAH REPUBLIK INDONESIA\n"
            "Menimbang: bahwa perlindungan pekerja diperlukan;\n"
            "Mengingat: Pasal 5 Undang-Undang Dasar;\n"
            "MEMUTUSKAN:\n"
            "Menetapkan: PERATURAN PEMERINTAH TENTANG PKWT.\n"
            "BAB I\nKETENTUAN UMUM\nPasal 1\n"
            "(1) Pekerja/buruh adalah setiap orang yang bekerja.\n"
            "(2) Pengusaha wajib memenuhi hak pekerja/buruh.",
        )
    ]

    sections = parse_legal_sections("PP-35-2021", pages)

    assert {section.type for section in sections} >= {
        "document",
        "menimbang",
        "mengingat",
        "memutuskan",
        "menetapkan",
        "bab",
        "pasal",
        "ayat",
    }
    bab = _section(sections, "bab", "BAB I")
    root = sections[0]
    pasal = _section(sections, "pasal", "Pasal 1")
    ayat = _section(sections, "ayat", "Ayat (1)")
    menetapkan = _section(sections, "menetapkan", "Menetapkan")
    memutuskan = _section(sections, "memutuskan", "Memutuskan")
    assert bab.title == "KETENTUAN UMUM"
    assert bab.role == "ketentuan_umum"
    assert bab.parent == root.node_id
    assert pasal.parent == bab.node_id
    assert ayat.parent == pasal.node_id
    assert menetapkan.parent == memutuskan.node_id


def test_uu_preserves_complete_bab_bagian_paragraf_pasal_ayat_hierarchy() -> None:
    pages = [
        _page(
            1,
            "BAB II\nHUBUNGAN KERJA\nBagian Kesatu\nUmum\n"
            "Paragraf 1\nPerjanjian Kerja\nPasal 5\n"
            "(1) Perjanjian kerja dibuat secara tertulis.",
        )
    ]

    sections = parse_legal_sections("UU-13-2003", pages)

    bab = _section(sections, "bab", "BAB II")
    bagian = _section(sections, "bagian", "Bagian Kesatu")
    paragraf = _section(sections, "paragraf", "Paragraf 1")
    pasal = _section(sections, "pasal", "Pasal 5")
    ayat = _section(sections, "ayat", "Ayat (1)")
    assert bagian.parent == bab.node_id
    assert paragraf.parent == bagian.node_id
    assert pasal.parent == paragraf.node_id
    assert ayat.parent == pasal.node_id
    assert [bab.order, bagian.order, paragraf.order, pasal.order, ayat.order] == sorted(
        [bab.order, bagian.order, paragraf.order, pasal.order, ayat.order]
    )


def test_pasal_and_ayat_continue_across_page_boundaries() -> None:
    pages = [
        _page(12, "Pasal 15\n(1) Pengusaha wajib memberikan"),
        _page(13, "uang kompensasi kepada pekerja/buruh.\n(2) Ketentuan lebih lanjut berlaku."),
    ]

    sections = parse_legal_sections("PP-35-2021", pages)

    pasal = _section(sections, "pasal", "Pasal 15")
    first_ayat = _section(sections, "ayat", "Ayat (1)")
    assert first_ayat.page_start == 12
    assert first_ayat.page_end == 13
    assert "memberikan\nuang kompensasi" in first_ayat.text
    assert pasal.page_start == 12
    assert pasal.page_end == 13
    assert "uang kompensasi kepada pekerja/buruh." in pasal.text


def test_cross_reference_and_running_header_do_not_create_orphan_or_duplicate_nodes() -> None:
    sections = parse_legal_sections(
        "UU-FIXTURE",
        [
            _page(7, "Pasal 8\n(1) Informasi ketenagakerjaan sebagaimana dimaksud dalam"),
            _page(
                8,
                "ayat\n(1), diperoleh dari semua pihak terkait.\n"
                "Pasal 8 ...\n(2) Data wajib diperbarui.",
            ),
        ],
    )

    pasals = [section for section in sections if section.type == "pasal"]
    ayats = [section for section in sections if section.type == "ayat"]
    assert [section.identifier for section in pasals] == ["Pasal 8"]
    assert [section.identifier for section in ayats] == ["Ayat (1)", "Ayat (2)"]
    assert all(section.parent == pasals[0].node_id for section in ayats)
    assert "ayat\n(1), diperoleh" in ayats[0].text


def test_pasal_references_do_not_create_duplicate_pasal_nodes() -> None:
    sections = parse_legal_sections(
        "PP-FIXTURE",
        [
            _page(
                1,
                "Pasal 12\nKetentuan berlaku.\n"
                "Pasal 12 sampai dengan Pasal 25 diatur dengan Peraturan Menteri.\n"
                "Pasal 13\nKetentuan lain berlaku.",
            )
        ],
    )

    assert [section.identifier for section in sections if section.type == "pasal"] == [
        "Pasal 12",
        "Pasal 13",
    ]


def test_pasal_with_many_ayat_creates_ordered_sibling_nodes() -> None:
    text = "Pasal 62\n" + "\n".join(
        f"({number}) Ketentuan ayat ke-{number}." for number in range(1, 7)
    )

    sections = parse_legal_sections("UU-FIXTURE", [_page(1, text)])

    pasal = _section(sections, "pasal", "Pasal 62")
    ayat = [section for section in sections if section.type == "ayat"]
    assert [section.identifier for section in ayat] == [
        "Ayat (1)",
        "Ayat (2)",
        "Ayat (3)",
        "Ayat (4)",
        "Ayat (5)",
        "Ayat (6)",
    ]
    assert all(section.parent == pasal.node_id for section in ayat)
    assert pasal.children == tuple(section.node_id for section in ayat)


def test_bagian_without_paragraf_parents_pasal_directly() -> None:
    pages = [_page(1, "BAB III\nBagian Kedua\nWaktu Kerja\nPasal 20\nIsi ketentuan.")]

    sections = parse_legal_sections("PP-FIXTURE", pages)

    bagian = _section(sections, "bagian", "Bagian Kedua")
    pasal = _section(sections, "pasal", "Pasal 20")
    assert bagian.title == "Waktu Kerja"
    assert pasal.parent == bagian.node_id
    assert not any(section.type == "paragraf" for section in sections)


def test_document_without_bab_parents_pasal_to_document() -> None:
    sections = parse_legal_sections(
        "PERMENAKER-FIXTURE",
        [_page(1, "Pasal 1\nPKWT dilaksanakan berdasarkan perjanjian kerja.")],
    )

    root = sections[0]
    pasal = _section(sections, "pasal", "Pasal 1")
    assert root.type == "document"
    assert pasal.parent == root.node_id


def test_penjelasan_is_a_new_scope_with_distinct_article_nodes() -> None:
    pages = [
        _page(
            1,
            "BAB I\nKETENTUAN UMUM\nPasal 1\nKetentuan normatif.\n"
            "PENJELASAN\nPasal 1\nCukup jelas.",
        )
    ]

    sections = parse_legal_sections("UU-FIXTURE", pages)

    articles = [section for section in sections if section.type == "pasal"]
    explanation = _section(sections, "penjelasan", "Penjelasan")
    assert len(articles) == 2
    assert articles[0].node_id != articles[1].node_id
    assert articles[1].parent == explanation.node_id
    assert "Pasal 1\nCukup jelas." in explanation.text


def test_lampiran_is_recognized_as_an_independent_document_scope() -> None:
    pages = [_page(4, "LAMPIRAN PERATURAN MENTERI NOMOR 1 TAHUN 2024\nFORMAT PKWT")]

    sections = parse_legal_sections("PERMEN-1-2024", pages)

    lampiran = _section(sections, "lampiran", "Lampiran")
    assert lampiran.page_start == 4
    assert lampiran.text.startswith("LAMPIRAN PERATURAN MENTERI")


def test_named_transition_and_closing_sections_are_recorded_as_bab_roles() -> None:
    pages = [
        _page(
            1,
            "BAB IV\nKETENTUAN PERALIHAN\nPasal 30\nKetentuan lama tetap berlaku.\n"
            "BAB V\nKETENTUAN PENUTUP\nPasal 31\nPeraturan ini mulai berlaku.",
        )
    ]

    sections = parse_legal_sections("PP-FIXTURE", pages)

    bab_iv = _section(sections, "bab", "BAB IV")
    bab_v = _section(sections, "bab", "BAB V")
    assert (bab_iv.title, bab_iv.role) == ("KETENTUAN PERALIHAN", "ketentuan_peralihan")
    assert (bab_v.title, bab_v.role) == ("KETENTUAN PENUTUP", "ketentuan_penutup")


def test_malformed_marker_starts_unstructured_node_instead_of_stale_pasal() -> None:
    pages = [_page(1, "BAB I\nPasal 1\nKetentuan pertama.\nPasal ???\nTeks rusak.")]

    sections = parse_legal_sections("BROKEN-FIXTURE", pages)

    pasal = _section(sections, "pasal", "Pasal 1")
    malformed = next(
        section
        for section in sections
        if section.type == "unstructured" and "Pasal ???" in section.text
    )
    assert "Teks rusak." in malformed.text
    assert "Pasal ???" not in pasal.text


def test_empty_pages_do_not_crash_or_invent_structure() -> None:
    sections = parse_legal_sections("EMPTY-FIXTURE", [_page(1, ""), _page(2, "")])

    assert len(sections) == 1
    assert sections[0].type == "document"
    assert sections[0].text == ""
    assert (sections[0].page_start, sections[0].page_end) == (1, 2)


def test_body_verbs_and_unit_names_do_not_reset_article_state() -> None:
    sections = parse_legal_sections(
        "UU-TEST",
        [
            _page(
                1,
                "Pasal 41\n(1) Pemerintah\nmenetapkan\nkebijakan.\n"
                "bagian/unit yang menangani K3.\n(2) Masyarakat mengawasi.",
            )
        ],
    )
    pasal = _section(sections, "pasal", "Pasal 41")
    assert all(n.parent == pasal.node_id for n in sections if n.type == "ayat")
    assert not any(n.type == "menetapkan" for n in sections)
    assert "bagian/unit" in pasal.text


def test_amendment_reference_does_not_create_second_article() -> None:
    sections = parse_legal_sections(
        "PP-TEST",
        [
            _page(
                1,
                "Pasal 4 dihapus, sehingga Pasal 4 berbunyi sebagai berikut:\n"
                "Pasal 4\n(1) Pekerja berhak.\nPENJEI.ASAN\nATAS\n"
                "Pasal 4\nCukup jelas.",
            )
        ],
    )
    assert len([n for n in sections if n.type == "pasal"]) == 2
    explanation = next(n for n in sections if n.type == "penjelasan")
    assert [n for n in sections if n.type == "pasal"][-1].parent == explanation.node_id


def test_annex_numbered_lists_are_not_orphan_ayat() -> None:
    sections = parse_legal_sections(
        "PP-TEST",
        [_page(1, "LAMPIRAN I\nPedoman K3\n(1) Pelaporan insiden.\n(2) Pelaporan bahaya.")],
    )
    assert len([n for n in sections if n.type == "list_item"]) == 2
    assert not any(n.type == "ayat" for n in sections)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "BAB I\nPasal 1\n(1) Isi.",
            {("bab", "BAB I"), ("pasal", "Pasal 1"), ("ayat", "Ayat (1)")},
        ),
        (
            "BAB II\nBagian Kesatu\nPasal 15",
            {("bab", "BAB II"), ("bagian", "Bagian Kesatu"), ("pasal", "Pasal 15")},
        ),
        (
            "BAB IV\nParagraf 2\nPasal 62\n(3) Isi.",
            {
                ("bab", "BAB IV"),
                ("paragraf", "Paragraf 2"),
                ("pasal", "Pasal 62"),
                ("ayat", "Ayat (3)"),
            },
        ),
        (
            "PENJELASAN\nPasal 1\nCukup jelas.",
            {("penjelasan", "Penjelasan"), ("pasal", "Pasal 1")},
        ),
    ],
)
def test_structure_detection_fixture_matrix_matches_expected_nodes_exactly(
    text: str,
    expected: set[tuple[str, str]],
) -> None:
    sections = parse_legal_sections("ACCURACY-FIXTURE", [_page(1, text)])
    detected = {
        (section.type, section.identifier)
        for section in sections
        if section.type not in {"document", "unstructured"}
    }

    assert detected == expected
