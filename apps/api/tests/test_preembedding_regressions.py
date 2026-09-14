import fitz
import pytest

from app.services.ingestion.artifacts import ArtifactStore
from app.services.ingestion.chunking import RegexTokenizer, chunk_legal_document
from app.services.ingestion.domain import Document, Page, StructuredLegalDocument
from app.services.ingestion.evaluation.evaluator import evaluate_ingestion
from app.services.ingestion.evaluation.preembedding import prepare_pages
from app.services.ingestion.evaluation.reporting import aggregate_ingestion_reports
from app.services.ingestion.pdf_extractor import (
    assess_text_quality,
    parse_pdf_pages,
    remove_repeated_margin_noise,
)
from app.services.ingestion.schemas import ExtractedPage
from app.services.ingestion.structure import parse_legal_sections


def document(text):
    pages = (Page(1, text, text),)
    return Document(
        document_id="PP-1-2025",
        title="Peraturan Pemerintah",
        source="JDIH",
        source_url="https://example.test/source",
        file_path=None,
        file_hash="a" * 64,
        page_count=1,
        metadata={},
        ingestion_version="test",
        pages=pages,
    )


def test_wrapped_lampiran_reference_does_not_clear_pasal():
    doc = document(
        "Pasal 1\n(1) Format tercantum dalam\nLampiran\n"
        "yang merupakan bagian tidak terpisahkan.\n(2) Ketentuan berlaku."
    )
    nodes = parse_legal_sections(doc.document_id, doc.pages)
    assert not any(node.type == "lampiran" for node in nodes)
    pasal = next(node for node in nodes if node.type == "pasal")
    assert len(pasal.children) == 2
    assert "Lampiran" in pasal.text


def test_spaced_penjelasan_resets_normative_scope():
    doc = document(
        "Pasal 1\nKetentuan berlaku.\nP E N J E L A S A N\nA T A S\nPasal 1\nCukup jelas"
    )
    nodes = parse_legal_sections(doc.document_id, doc.pages)
    explanation = next(node for node in nodes if node.type == "penjelasan")
    assert [node for node in nodes if node.type == "pasal"][-1].parent == explanation.node_id


def test_short_explanations_are_not_broken_word_spacing():
    text = "\n".join(f"Pasal {i}\nAyat (1)\nCukup jelas" for i in range(1, 30))
    score, flags = assess_text_quality(text)
    assert score >= 0.65
    assert "missing_word_spaces" not in flags
    assert assess_text_quality("\n".join(f"Pasal {i}\nDihapus." for i in range(30)))[0] >= 0.65
    assert assess_text_quality("\n".join(["pekerja", "wajib", "menerima"] * 20))[0] < 0.65


def test_compact_headings_and_ayat_survive_repeated_margin_removal():
    pages = [
        ExtractedPage(
            page_number=i,
            text=f"Pasal2\n(1)\nHak pekerja berlaku {i}.",
            text_length=40,
            requires_ocr=False,
        )
        for i in range(1, 5)
    ]
    for page in remove_repeated_margin_noise(pages):
        assert "Pasal2" in page.text
        assert "(1)" in page.text


def test_spatial_reading_order_keeps_content_stream_raw(tmp_path):
    path = tmp_path / "out-of-order.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 150), "Pasal 2")
        page.insert_text((72, 72), "Pasal 1")
        pdf.save(path)
    page = parse_pdf_pages(path, detect_tables=False)[0]
    assert page.raw_text.index("Pasal 2") < page.raw_text.index("Pasal 1")
    assert page.cleaned_text.index("Pasal 1") < page.cleaned_text.index("Pasal 2")


def test_cross_reference_metadata_is_not_claimed_as_article_ownership():
    doc = document(
        "Menimbang: pelaksanaan ketentuan\nPasal 15 ayat (1) diperlukan.\n"
        "Pasal 1\nPekerja mendapat perlindungan."
    )
    nodes = tuple(parse_legal_sections(doc.document_id, doc.pages))
    result = chunk_legal_document(StructuredLegalDocument(doc, nodes), tokenizer=RegexTokenizer())
    report = evaluate_ingestion(doc, nodes, result.chunks, scope="through_metadata")
    assert not report.metadata["missing_pasal_chunk_ids"]
    assert not any(f.code == "metadata.chunk_provenance_invalid" for f in report.findings)
    corpus = aggregate_ingestion_reports([report.to_dict()])
    assert corpus.scope == "through_metadata"
    assert corpus.totals["embedding_success_rate"] is None
    assert corpus.totals["index_consistency"] is None


def test_metadata_scope_still_fails_true_duplicate_articles():
    doc = document("Pasal 1\nCukup jelas.\nPasal 1\nCukup jelas.")
    nodes = tuple(parse_legal_sections(doc.document_id, doc.pages))
    chunks = chunk_legal_document(
        StructuredLegalDocument(doc, nodes), tokenizer=RegexTokenizer()
    ).chunks
    report = evaluate_ingestion(doc, nodes, chunks, scope="through_metadata")
    assert report.status == "FAIL"
    assert any(f.code == "structure.duplicate_pasal_identifiers" for f in report.findings)


def test_cache_reuses_raw_pages_without_embedding_or_indexing(tmp_path, monkeypatch):
    path = tmp_path / "normal.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Pasal 1 Pekerja berhak atas perlindungan sesuai peraturan.")
        pdf.save(path)
    store = ArtifactStore(tmp_path / "artifacts")
    first, _ = prepare_pages(path, "a" * 64, store, ocr=False)
    monkeypatch.setattr(
        "app.services.ingestion.evaluation.preembedding.extract_pages",
        lambda *a, **k: pytest.fail("cache must avoid re-extraction"),
    )
    second, _ = prepare_pages(path, "a" * 64, store, ocr=False)
    assert first == second


def test_amended_regulations_get_distinct_explicit_scopes():
    doc = document(
        "Pasal 10\nBeberapa ketentuan dalam Undang-Undang Nomor 1 diubah:\n"
        "Pasal 1\nPekerja berhak atas upah.\n"
        "Pasal 11\nBeberapa ketentuan dalam Undang-Undang Nomor 2 diubah:\n"
        "Pasal 1\nPengusaha wajib membayar upah."
    )
    nodes = parse_legal_sections(doc.document_id, doc.pages)
    quotes = [node for node in nodes if node.identifier == "Pasal 1"]
    assert len(quotes) == 2
    assert quotes[0].amendment_scope != quotes[1].amendment_scope
    assert all(node.amendment_scope for node in quotes)


def test_spaced_ocr_article_number_keeps_amendment_provenance():
    doc = document(
        "Pasal 1 1 1\nBeberapa ketentuan dalam Undang-Undang Nomor 7 diubah:\n"
        "Pasal 13\nKetentuan pajak berlaku."
    )
    nodes = parse_legal_sections(doc.document_id, doc.pages)
    owner = next(node for node in nodes if node.identifier == "Pasal 111")
    target = next(node for node in nodes if node.identifier == "Pasal 13")
    assert target.amendment_scope == owner.node_id


def test_nested_amendment_items_get_distinct_source_marker_scopes():
    doc = document(
        "Bagian Kesatu\nPerubahan\n"
        "1. Ketentuan Pasal 1 diubah sehingga berbunyi sebagai berikut:\n"
        "Pasal 1\nKetentuan pertama.\n"
        "2. Ketentuan Pasal 1 diubah sehingga berbunyi sebagai berikut:\n"
        "Pasal 1\nKetentuan kedua."
    )
    nodes = parse_legal_sections(doc.document_id, doc.pages)
    targets = [node for node in nodes if node.identifier == "Pasal 1"]
    assert len(targets) == 2
    assert all(node.amendment_scope for node in targets)
    assert targets[0].amendment_scope != targets[1].amendment_scope


def test_repeated_explanation_pasal_can_start_a_new_angka_block():
    doc = document(
        "PENJELASAN\nAngka 10\nPasal 62\nCukup jelas.\n"
        "Pasal 62\nAngka 1\nPasal 5\nCukup jelas."
    )
    nodes = parse_legal_sections(doc.document_id, doc.pages)
    articles = [node for node in nodes if node.identifier == "Pasal 62"]
    assert len(articles) == 2
    assert all(node.amendment_scope for node in articles)
    assert articles[0].amendment_scope != articles[1].amendment_scope


def test_ocr_zero_in_article_number_starts_a_new_amendment_scope():
    doc = document(
        "Pasal 1O8\nBeberapa ketentuan dalam Undang-Undang Nomor 20 diubah:\n"
        "Pasal 20\nKetentuan Merek."
    )
    nodes = parse_legal_sections(doc.document_id, doc.pages)
    owner = next(node for node in nodes if node.identifier == "Pasal 108")
    target = next(node for node in nodes if node.identifier == "Pasal 20")
    assert target.amendment_scope == owner.node_id


def test_adjacent_page_catchword_does_not_create_empty_article():
    pages = (
        Page(1, "", "Pasal 1\nPekerja berhak atas upah.\nPasal 2"),
        Page(2, "", "REPUBLIK INDONESIA\nPasal 2\n(1) Upah dibayarkan."),
    )
    nodes = parse_legal_sections("PP-1-2025", pages)
    assert [node.identifier for node in nodes if node.type == "pasal"] == ["Pasal 1", "Pasal 2"]
    assert next(node for node in nodes if node.type == "ayat").parent == nodes[-2].node_id


def test_ocr_margin_bar_and_heading_comma_keep_ayat_parent():
    doc = document("BAB VIII\nPEMBAYARAN UPAH\n| Pasal 53,\n(1) Upah dibayar.")
    nodes = parse_legal_sections(doc.document_id, doc.pages)
    pasal = next(node for node in nodes if node.type == "pasal")
    assert pasal.identifier == "Pasal 53"
    assert nodes[-1].parent == pasal.node_id


def test_omnibus_explanations_retain_explicit_enacting_article_scope():
    doc = document(
        "PENJELASAN\nPasal 17\nAngka 1\nPasal 1\nCukup jelas.\n"
        "Pasal 18\nAngka 1\nPasal 1\nCukup jelas."
    )
    nodes = parse_legal_sections(doc.document_id, doc.pages)
    quoted = [node for node in nodes if node.identifier == "Pasal 1"]
    owners = {
        node.identifier: node.node_id
        for node in nodes
        if node.identifier in {"Pasal 17", "Pasal 18"}
    }
    assert [node.amendment_scope for node in quoted] == [owners["Pasal 17"], owners["Pasal 18"]]


def test_repeated_official_provision_pair_is_preserved_but_not_indexed_twice():
    doc = document(
        "PENJELASAN\nPasal 80\nCukup jelas.\nPasal 81\nCukup jelas.\n"
        "Pasal 80\nCukup jelas.\nPasal 81\nCukup jelas."
    )
    nodes = tuple(parse_legal_sections(doc.document_id, doc.pages))
    repeated = [node for node in nodes if node.source_duplicate_of]
    assert [node.identifier for node in repeated] == ["Pasal 80", "Pasal 81"]
    assert [node.page_start for node in repeated] == [1, 1]

    chunks = chunk_legal_document(
        StructuredLegalDocument(doc, nodes), tokenizer=RegexTokenizer()
    ).chunks
    assert [chunk.legal_hierarchy["pasal"] for chunk in chunks] == ["80", "81"]
    report = evaluate_ingestion(doc, nodes, chunks, scope="through_metadata")
    assert report.status == "PASS"
    assert report.structure["source_duplicate_sections"] == [
        repeated[0].node_id,
        repeated[1].node_id,
    ]


def test_failed_ocr_keeps_raw_and_actionable_diagnostics(tmp_path, monkeypatch):
    from app.services.ingestion.pdf_extractor import apply_page_ocr_fallback

    path = tmp_path / "scan.pdf"
    with fitz.open() as pdf:
        pdf.new_page()
        pdf.save(path)
    monkeypatch.setattr(
        "app.services.ingestion.pdf_extractor._available_ocr_language", lambda: "ind"
    )

    def fail(*args):
        raise RuntimeError("OCR timeout")

    monkeypatch.setattr("app.services.ingestion.pdf_extractor._ocr_page_with_tesseract", fail)
    page = ExtractedPage(
        page_number=1, text="source", raw_text="ORIGINAL", text_length=6, requires_ocr=True
    )
    result = apply_page_ocr_fallback(path, [page], page_numbers=[1])[0]
    assert result.raw_text == "ORIGINAL"
    assert result.requires_ocr
    assert "ocr_page_fallback_failed" in result.quality_flags
    assert "ocr_error=OCR timeout" in result.quality_flags
