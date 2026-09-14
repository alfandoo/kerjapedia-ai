from types import SimpleNamespace

from app.services.rag.chunking import (
    ChunkingConfig,
    build_chunks,
    split_sentences,
)


def make_segment(article, paragraph, text, page=1):
    return SimpleNamespace(
        document_id="PP-35-2021",
        chapter="BAB II",
        section=None,
        article=article,
        paragraph=paragraph,
        page_start=page,
        page_end=page,
        text=text,
    )


def build(**overrides):
    segments = overrides.pop("segments")
    return build_chunks(
        segments,
        document_id="PP-35-2021",
        short_title="PP 35/2021",
        version=7,
        **overrides,
    )


def test_abbreviations_survive_sentence_splitting() -> None:
    sentences = split_sentences(
        "Menurut PP No. 35 Tahun 2021 pekerja dibayar Rp. 100. Lima ayat dkk. berlaku."
    )

    assert sentences == [
        "Menurut PP No. 35 Tahun 2021 pekerja dibayar Rp. 100.",
        "Lima ayat dkk. berlaku.",
    ]


def test_ayat_stays_whole_when_it_fits() -> None:
    segments = [make_segment("Pasal 15", "Ayat (1)", "Pengusaha wajib memberikan uang kompensasi.")]

    chunks = build(segments=segments)

    assert len(chunks) == 1
    assert chunks[0].article == "Pasal 15"
    assert chunks[0].parts == 1
    assert chunks[0].retrieval_text.startswith("PP 35/2021 | Pasal 15 | Ayat (1)")


def test_oversized_ayat_splits_with_parts_and_overlap() -> None:
    sentences = " ".join(f"Kalimat ketentuan nomor {number} berlaku umum." for number in range(40))
    segments = [make_segment("Pasal 15", "Ayat (1)", sentences)]
    config = ChunkingConfig(target_tokens=30, max_tokens=100, overlap_sentences=2)

    chunks = build(segments=segments, config=config)

    assert len(chunks) > 1
    assert all(chunk.parts == len(chunks) for chunk in chunks)
    assert chunks[0].retrieval_text.startswith("PP 35/2021 | Pasal 15 | Ayat (1) (bagian 1 dari")
    assert all(chunk.continued for chunk in chunks)
    overlap = chunks[1].text.split(". ")[0]
    assert overlap in chunks[0].text


def test_short_same_article_segments_coalesce_but_articles_never_merge() -> None:
    segments = [
        make_segment("Pasal 15", "Ayat (1)", "Isi ayat satu."),
        make_segment("Pasal 15", "Ayat (2)", "Isi ayat dua."),
        make_segment("Pasal 16", "Ayat (1)", "Isi pasal enam belas."),
    ]
    config = ChunkingConfig(target_tokens=100, max_tokens=500, min_merge_tokens=100)

    chunks = build(segments=segments, config=config)

    assert len(chunks) == 2
    assert chunks[0].article == "Pasal 15"
    assert chunks[0].paragraph is None
    assert "Isi ayat satu." in chunks[0].text and "Isi ayat dua." in chunks[0].text


def test_chunk_ids_are_stable_across_rebuilds() -> None:
    segments = [make_segment("Pasal 15", "Ayat (1)", "Pengusaha wajib memberikan uang kompensasi.")]

    first = build(segments=segments)
    second = build(segments=segments)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert first[0].chunk_id.startswith("PP-35-2021-v7-")


def test_parent_text_carries_article_context() -> None:
    segments = [
        make_segment("Pasal 15", "Ayat (1)", "Isi ayat satu tentang kompensasi."),
        make_segment("Pasal 15", "Ayat (2)", "Isi ayat dua tentang pembayaran."),
    ]
    config = ChunkingConfig(target_tokens=100, max_tokens=500, min_merge_tokens=100)

    chunks = build(segments=segments, config=config)

    assert "kompensasi" in chunks[0].parent_text and "pembayaran" in chunks[0].parent_text
