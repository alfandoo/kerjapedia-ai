import pytest

from app.services.ingestion.chunker import build_chunks
from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.ingestion.legal_parser import normalize_legal_line, parse_legal_segments
from app.services.ingestion.pipeline import document_version_from_checksum
from app.services.ingestion.schemas import DocumentMetadata, ExtractedPage


def sample_document() -> DocumentMetadata:
    return DocumentMetadata(
        document_id="PP-35-2021",
        title="Peraturan Pemerintah Nomor 35 Tahun 2021",
        short_title="PP 35/2021",
        regulation_type="PP",
        number=35,
        year=2021,
        issuer="Pemerintah Republik Indonesia",
        topics=["pkwt"],
        legal_status="needs_verification",
        source_name="Database Peraturan JDIH BPK",
        source_url="https://peraturan.bpk.go.id/",
        local_file="dataset/example.pdf",
        file_name="example.pdf",
        size_bytes=1,
        sha256="abcd" * 16,
        verification_status="pending_detail_url",
    )


def test_parse_legal_segments_tracks_article_and_paragraph() -> None:
    pages = [
        ExtractedPage(
            page_number=1,
            text="BAB II\nKETENAGAKERJAAN\nPasal 15\n(1) Pekerja berhak atas kompensasi.",
            text_length=74,
            requires_ocr=False,
        )
    ]

    segments = parse_legal_segments("PP-35-2021", pages)

    assert any(segment.chapter == "BAB II" for segment in segments)
    assert any(segment.article == "Pasal 15" for segment in segments)
    assert any(segment.paragraph == "Ayat (1)" for segment in segments)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Pasal5", "Pasal 5"),
        ("Pasa14", "Pasal 4"),
        ("Pasall0", "Pasal 10"),
        ("BABI", "BAB I"),
        ("THRKeagamaan wajib dibayar", "THR Keagamaan wajib dibayar"),
    ],
)
def test_normalize_legal_line_repairs_common_pdf_artifacts(
    raw: str,
    expected: str,
) -> None:
    assert normalize_legal_line(raw) == expected


def test_parse_compact_article_keeps_paragraph_on_correct_article() -> None:
    pages = [
        ExtractedPage(
            page_number=5,
            text=(
                "Pasal5\n"
                "(1) THR sebagaimana dimaksud dalam Pasal2 diberikan satu kali.\n"
                "(4) THRKeagamaan wajib dibayarkan paling lambat 7 hari sebelum hari raya.\n"
                "Pasa14\n"
                "Ketentuan lain berlaku."
            ),
            text_length=140,
            requires_ocr=False,
        )
    ]

    segments = parse_legal_segments("PERMENAKER-6-2016", pages)
    deadline = next(segment for segment in segments if "7 hari" in segment.text)

    assert deadline.article == "Pasal 5"
    assert deadline.paragraph == "Ayat (4)"
    assert "THR Keagamaan" in deadline.text
    assert any(segment.article == "Pasal 4" for segment in segments)
    assert not any(segment.article == "Pasal 2" for segment in segments)


def test_build_chunks_preserves_legal_metadata() -> None:
    pages = [
        ExtractedPage(
            page_number=3,
            text="Pasal 1\n(1) Setiap pekerja memiliki hak.",
            text_length=42,
            requires_ocr=False,
        )
    ]
    segments = parse_legal_segments("PP-35-2021", pages)

    chunks = build_chunks(sample_document(), segments, version=1, max_chars=100)

    assert chunks
    assert chunks[0].document_id == "PP-35-2021"
    assert chunks[0].article == "Pasal 1"
    assert chunks[0].topics == ["pkwt"]


def test_hash_embedding_is_deterministic_and_normalized() -> None:
    provider = HashEmbeddingProvider(dimensions=8)

    first = provider.embed(["kompensasi pkwt"])[0]
    second = provider.embed(["kompensasi pkwt"])[0]

    assert first == second
    assert len(first) == 8
    assert sum(value * value for value in first) == pytest.approx(1.0, rel=1e-6)


def test_document_version_uses_checksum_prefix() -> None:
    assert document_version_from_checksum("0000000f" + "a" * 56) == 15
