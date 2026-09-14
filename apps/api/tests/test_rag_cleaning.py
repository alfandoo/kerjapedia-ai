from app.services.rag.cleaning import (
    deduplicate_indices,
    duplicate_groups,
    evaluate_cleaning,
    missing_article_numbers,
)
from app.services.rag.extraction import normalize_text


def test_paragraph_breaks_survive_normalization() -> None:
    assert normalize_text("aturan satu.\n\n\naturan dua.") == "aturan satu.\n\naturan dua."
    assert normalize_text("baris satu.\nbaris dua.") == "baris satu.\nbaris dua."


def test_article_continuity_exposes_parser_blind_spots() -> None:
    assert missing_article_numbers({"Pasal 1", "Pasal 4", "Pasal 6"}) == [2, 3, 5]
    assert missing_article_numbers({"Pasal 1", "Pasal 2", "Pasal 3"}) == []
    assert missing_article_numbers(set()) == []


def test_dedup_keeps_first_occurrence_and_reports_rest() -> None:
    texts = ["Aturan upah.", "Aturan cuti.", "aturan  upah.", "Aturan lembur."]

    assert duplicate_groups(texts) == [[0, 2]]
    kept, removed = deduplicate_indices(texts)
    assert kept == [0, 1, 3]
    assert removed == [2]


def test_empty_detection_blocks_with_clear_message() -> None:
    report = evaluate_cleaning(
        detected_articles=set(),
        chunk_articles=set(),
        final_texts=[],
        unresolved_pages=[],
        heading_only_ids=[],
        margin_noise_ids=[],
        token_counts=[],
        max_tokens=550,
    )

    by_id = {gate.gate_id: gate for gate in report.gates}
    assert report.status == "review_required"
    assert by_id["articles_detected"].severity == "block"
    assert by_id["articles_detected"].passed is False


def test_lost_articles_block_but_cosmetics_only_warn() -> None:
    report = evaluate_cleaning(
        detected_articles={"Pasal 1", "Pasal 4", "Pasal 6"},
        chunk_articles={"Pasal 1", "Pasal 4", "Pasal 6"},
        final_texts=["a", "b"],
        unresolved_pages=[7],
        heading_only_ids=["chunk-h"],
        margin_noise_ids=[],
        token_counts=[100, 200],
        max_tokens=550,
    )

    assert report.status == "review_required"
    by_id = {gate.gate_id: gate for gate in report.gates}
    assert by_id["article_continuity"].severity == "block"
    assert by_id["article_continuity"].passed is False
    assert by_id["unresolved_pages"].severity == "warn"
    assert any("unresolved_pages" in warning for warning in report.warnings)
    assert report.stats["missing_articles"] == [2, 3, 5]


def test_clean_build_passes_with_warnings_only() -> None:
    report = evaluate_cleaning(
        detected_articles={"Pasal 1", "Pasal 2"},
        chunk_articles={"Pasal 1", "Pasal 2"},
        final_texts=["a", "b"],
        unresolved_pages=[],
        heading_only_ids=[],
        margin_noise_ids=["chunk-m"],
        token_counts=[100],
        max_tokens=550,
    )

    assert report.status == "passed"
    assert any("margin_noise_in_chunks" in warning for warning in report.warnings)


def test_unchunked_articles_and_overlong_chunks_block() -> None:
    report = evaluate_cleaning(
        detected_articles={"Pasal 1", "Pasal 2"},
        chunk_articles={"Pasal 1"},
        final_texts=["a", "a"],
        unresolved_pages=[],
        heading_only_ids=[],
        margin_noise_ids=[],
        token_counts=[100, 900],
        max_tokens=550,
    )

    by_id = {gate.gate_id: gate for gate in report.gates}
    assert report.status == "review_required"
    assert by_id["detected_articles_chunked"].passed is False
    assert by_id["no_duplicate_texts"].passed is False
    assert by_id["max_chunk_tokens"].passed is False
