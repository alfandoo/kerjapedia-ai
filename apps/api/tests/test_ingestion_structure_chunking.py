from __future__ import annotations

import statistics
from pathlib import Path

from app.services.ingestion.chunking import (
    ChunkingConfig,
    RegexTokenizer,
    chunk_legal_document,
)
from app.services.ingestion.domain import Document, Page, StructuredLegalDocument
from app.services.ingestion.structure import parse_legal_sections


def _structured(page_texts: list[tuple[int, str]], document_id: str = "PP-35-2021"):
    pages = tuple(
        Page(page_number=number, raw_text=text, cleaned_text=text)
        for number, text in page_texts
    )
    document = Document(
        document_id=document_id,
        title="Peraturan Pemerintah Nomor 35 Tahun 2021",
        source="JDIH BPK",
        source_url="https://peraturan.bpk.go.id/Details/161904/pp-no-35-tahun-2021",
        file_path=Path("dataset/PP Nomor 35 Tahun 2021.pdf"),
        file_hash="a" * 64,
        page_count=len(pages),
        metadata={"regulation_type": "PP", "number": 35, "year": 2021},
        ingestion_version="v3",
        pages=pages,
    )
    sections = parse_legal_sections(document_id, pages, document_title=document.title)
    return StructuredLegalDocument(document=document, sections=tuple(sections))


def _chunk(structured, *, target=40, maximum=60, minimum=8, overlap=6):
    return chunk_legal_document(
        structured,
        tokenizer=RegexTokenizer(),
        config=ChunkingConfig(
            target_tokens=target,
            max_tokens=maximum,
            min_tokens=minimum,
            overlap_tokens=overlap,
        ),
    )


def test_very_short_pasal_remains_one_useful_legal_chunk() -> None:
    structured = _structured([(1, "Pasal 1\nPKWT berlaku.")])

    result = _chunk(structured)

    assert len(result.chunks) == 1
    assert result.chunks[0].content == "Pasal 1\nPKWT berlaku."
    assert result.chunks[0].legal_hierarchy == {"pasal": "1"}
    assert result.chunks[0].metadata["overlap_tokens"] == 0


def test_normal_pasal_stays_whole_even_when_above_target_but_below_maximum() -> None:
    body = " ".join(f"ketentuan{number}" for number in range(35)) + "."
    structured = _structured([(1, f"Pasal 15\n{body}")])

    result = _chunk(structured, target=20, maximum=60)

    assert len(result.chunks) == 1
    assert result.chunks[0].content.startswith("Pasal 15\n")
    assert result.chunks[0].token_count > 20
    assert result.chunks[0].token_count <= 60


def test_long_pasal_splits_at_ayat_boundaries() -> None:
    first = " ".join(f"hak{number}" for number in range(18)) + "."
    second = " ".join(f"kewajiban{number}" for number in range(18)) + "."
    structured = _structured([(1, f"Pasal 15\n(1) {first}\n(2) {second}")])

    result = _chunk(structured, target=22, maximum=30)

    assert len(result.chunks) == 2
    assert [chunk.legal_hierarchy["ayat"] for chunk in result.chunks] == ["1", "2"]
    assert all(chunk.content.startswith("Pasal 15\n(") for chunk in result.chunks)
    assert all(chunk.chunk_type == "ayat" for chunk in result.chunks)


def test_many_ayat_are_independent_and_retain_their_order() -> None:
    ayat_text = "\n".join(
        f"({number}) Ketentuan untuk pekerja nomor {number}." for number in range(1, 9)
    )
    structured = _structured([(1, f"Pasal 20\n{ayat_text}")])

    result = _chunk(structured, target=20, maximum=30)

    assert len(result.chunks) == 8
    assert [chunk.legal_hierarchy["ayat"] for chunk in result.chunks] == [
        str(number) for number in range(1, 9)
    ]
    assert [chunk.part_number for chunk in result.chunks] == [1] * 8


def test_pasal_spanning_pages_preserves_the_complete_page_range() -> None:
    structured = _structured(
        [
            (12, "Pasal 15\n(1) Pengusaha wajib memberikan"),
            (13, "uang kompensasi kepada pekerja/buruh."),
        ]
    )

    result = _chunk(structured)

    assert len(result.chunks) == 1
    assert result.chunks[0].page_start == 12
    assert result.chunks[0].page_end == 13
    assert "memberikan\nuang kompensasi" in result.chunks[0].content


def test_large_pasal_without_ayat_uses_token_fallback_and_keeps_marker() -> None:
    sentences = " ".join(
        f"Ketentuan kompensasi nomor {number} tetap berlaku." for number in range(20)
    )
    structured = _structured([(1, f"Pasal 21\n{sentences}")])

    result = _chunk(structured, target=24, maximum=32, overlap=5)

    assert len(result.chunks) > 1
    assert all(chunk.content.startswith("Pasal 21\n") for chunk in result.chunks)
    assert all(chunk.chunk_type == "pasal_continuation" for chunk in result.chunks)
    assert any(chunk.metadata["overlap_tokens"] > 0 for chunk in result.chunks[:-1])


def test_enormous_ayat_falls_back_to_tokens_without_losing_pasal_or_ayat_marker() -> None:
    sentences = " ".join(
        f"Pengusaha membayar kompensasi tahap {number}." for number in range(30)
    )
    structured = _structured([(1, f"Pasal 62\n(1) {sentences}")])

    result = _chunk(structured, target=25, maximum=34, overlap=4)

    assert len(result.chunks) > 1
    assert all(chunk.content.startswith("Pasal 62\n(1) ") for chunk in result.chunks)
    assert all(chunk.legal_hierarchy["pasal"] == "62" for chunk in result.chunks)
    assert all(chunk.legal_hierarchy["ayat"] == "1" for chunk in result.chunks)
    assert [chunk.part_number for chunk in result.chunks] == list(
        range(1, len(result.chunks) + 1)
    )
    assert all(chunk.part_count == len(result.chunks) for chunk in result.chunks)


def test_complete_hierarchy_and_source_provenance_are_attached() -> None:
    body = " ".join(f"ketentuan{number}" for number in range(35)) + "."
    structured = _structured(
        [
            (
                1,
                "BAB III\nKETENTUAN UMUM\nBagian Kesatu\nUmum\n"
                f"Paragraf 1\nPKWT\nPasal 15\n(1) {body}\n(2) Isi kedua.",
            )
        ]
    )

    result = _chunk(structured, target=24, maximum=32)
    ayat = next(chunk for chunk in result.chunks if chunk.legal_hierarchy.get("ayat") == "1")

    assert ayat.legal_hierarchy == {
        "bab": "III",
        "role": "ketentuan_umum",
        "bagian": "Kesatu",
        "paragraf": "1",
        "pasal": "15",
        "ayat": "1",
    }
    assert ayat.section_path == (
        "BAB III",
        "Bagian Kesatu",
        "Paragraf 1",
        "Pasal 15",
        "Ayat (1)",
    )
    assert ayat.source == "JDIH BPK"
    assert ayat.source_url == structured.document.source_url
    assert ayat.metadata["file_hash"] == "a" * 64


def test_chunk_ids_and_content_hashes_are_deterministic() -> None:
    structured = _structured([(1, "Pasal 15\n(1) Pengusaha membayar kompensasi.")])

    first = _chunk(structured)
    second = _chunk(structured)

    assert [chunk.chunk_id for chunk in first.chunks] == [
        chunk.chunk_id for chunk in second.chunks
    ]
    assert [chunk.content_hash for chunk in first.chunks] == [
        chunk.content_hash for chunk in second.chunks
    ]


def test_opening_and_annex_are_preserved_when_document_also_has_articles() -> None:
    structured = _structured([(1, "Menimbang: perlindungan pekerja diperlukan.\n"
        "Pasal 1\nKewajiban berlaku.\nLAMPIRAN I\nPedoman keselamatan.\n"
        "(1) Catat insiden.\n(2) Laporkan bahaya.")])
    result = _chunk(structured)
    content = "\n".join(c.content for c in result.chunks)
    assert "perlindungan pekerja diperlukan" in content
    assert "Pedoman keselamatan" in content
    assert "Catat insiden" in content
    assert content.count("Laporkan bahaya") == 1


def test_every_emitted_chunk_respects_the_hard_token_maximum() -> None:
    text = " ".join(f"kata{number}" for number in range(300))
    structured = _structured([(1, f"Pasal 62\n(1) {text}")])

    result = _chunk(structured, target=20, maximum=27, minimum=7, overlap=3)

    assert result.chunks
    assert all(0 < chunk.token_count <= 27 for chunk in result.chunks)
    assert result.statistics.max_tokens <= 27


def test_chunk_statistics_report_distribution_from_actual_token_counts() -> None:
    ayat_text = "\n".join(
        f"({number}) " + " ".join(["kata"] * (number * 3)) + "."
        for number in range(1, 6)
    )
    structured = _structured([(1, f"Pasal 30\n{ayat_text}")])

    result = _chunk(structured, target=20, maximum=25)
    counts = [chunk.token_count for chunk in result.chunks]
    stats = result.statistics

    assert stats.number_of_chunks == len(counts)
    assert stats.min_tokens == min(counts)
    assert stats.max_tokens == max(counts)
    assert stats.mean_tokens == statistics.fmean(counts)
    assert stats.median_tokens == statistics.median(counts)
    assert stats.p95_tokens >= stats.median_tokens
    assert stats.p99_tokens >= stats.p95_tokens
