from app.services.rag.metadata import (
    build_artifact,
    build_index_metadata,
    detect_language,
    extract_key_terms,
    validate_index_metadata,
)


def full_metadata(**overrides):
    base = {
        "chunk_id": "PP-35-2021-v7-abc123",
        "document_id": "PP-35-2021",
        "version": 7,
        "short_title": "PP 35/2021",
        "topics_chunk": ["pkwt"],
        "segment_kind": "substantive",
        "legal_status": "active",
        "source_url": "https://peraturan.bpk.go.id/Details/161904",
        "article": "Pasal 15",
        "text": "Pengusaha wajib memberikan uang kompensasi.",
        "retrieval_text": "PP 35/2021 | Pasal 15 | Pengusaha wajib memberikan uang kompensasi.",
        "quality_score": 0.9,
        "language": "id",
        "embedding_model": "BAAI/bge-m3",
        "embedding_revision": "pinned",
    }
    base.update(overrides)
    return build_index_metadata(**base)


def test_index_metadata_validates_clean() -> None:
    assert validate_index_metadata(full_metadata()) == []


def test_validation_names_every_missing_key() -> None:
    metadata = full_metadata()
    del metadata["article"]
    del metadata["embedding_model"]

    assert validate_index_metadata(metadata) == ["article", "embedding_model"]


def test_chunk_layers_and_kind_survive() -> None:
    metadata = full_metadata(topics_doc=["pkwt", "phk"], topics_chunk=["pkwt"])

    assert metadata["topics_doc"] == ["pkwt", "phk"]
    assert metadata["topics_chunk"] == ["pkwt"]
    assert metadata["segment_kind"] == "substantive"


def test_parent_text_stays_out_of_the_index() -> None:
    metadata = full_metadata()
    artifact = build_artifact(
        chunk_id="c1", document_id="PP-35-2021", parent_text="konteks luas"
    )

    assert "parent_text" not in metadata
    assert artifact.parent_text == "konteks luas"


def test_key_terms_keep_operative_words_and_numbers() -> None:
    terms = extract_key_terms("Pengusaha wajib memberikan uang kompensasi 7 hari.")

    assert "kompensasi" in terms
    assert "pengusaha" in terms
    assert "7" in terms
    assert "yang" not in terms


def test_language_tags_id_and_en() -> None:
    assert detect_language("Pekerja berhak atas upah dan tunjangan hari raya.") == "id"
    assert detect_language("The employee is entitled to wages and the article shall apply.") == "en"
