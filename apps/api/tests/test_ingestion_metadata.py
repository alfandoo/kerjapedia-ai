from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.models.ingestion import DocumentChunk
from app.services.ingestion.chunking import ChunkingConfig, RegexTokenizer, chunk_legal_document
from app.services.ingestion.domain import (
    Document,
    Page,
    StructuredLegalDocument,
    content_sha256,
)
from app.services.ingestion.provenance import (
    MetadataContext,
    MetadataValidationError,
    build_legacy_chunk_provenance,
    enrich_chunk_metadata,
    metadata_sha256,
    validate_provenance_payload,
)
from app.services.ingestion.schemas import Chunk as LegacyChunk
from app.services.ingestion.schemas import DocumentMetadata as LegacyDocumentMetadata
from app.services.ingestion.structure import parse_legal_sections

FIXED_TIME = datetime(2026, 9, 13, 8, 30, tzinfo=UTC)


def _input():
    text = (
        "BAB III\nKETENTUAN UMUM\nBagian Kesatu\nUmum\nParagraf 1\nPKWT\n"
        "Pasal 15\n(1) Pengusaha wajib memberikan kompensasi."
    )
    page = Page(page_number=1, raw_text=text, cleaned_text=text)
    document = Document(
        document_id="PP-35-2021",
        title="Peraturan Pemerintah Nomor 35 Tahun 2021",
        source="JDIH BPK",
        source_url="https://peraturan.bpk.go.id/Details/161904/pp-no-35-tahun-2021",
        file_path=Path("dataset/PP Nomor 35 Tahun 2021.pdf"),
        file_hash="a" * 64,
        page_count=1,
        metadata={
            "regulation_type": "PP",
            "number": 35,
            "year": 2021,
            "legal_status": "berlaku",
        },
        ingestion_version="v3",
        pages=(page,),
    )
    sections = parse_legal_sections(document.document_id, document.pages)
    structured = StructuredLegalDocument(document=document, sections=tuple(sections))
    chunks = chunk_legal_document(
        structured,
        tokenizer=RegexTokenizer(),
        config=ChunkingConfig(target_tokens=40, max_tokens=60, min_tokens=8),
    ).chunks
    context = MetadataContext(
        parser_version="kerjapedia-legal-structure-v3",
        chunker_version="kerjapedia-structure-aware-chunker-v3",
        embedding_model="BAAI/bge-m3@5617a9f",
        created_at=FIXED_TIME,
    )
    return structured, chunks, context


def test_metadata_is_classified_into_four_operational_levels() -> None:
    structured, chunks, context = _input()

    metadata = enrich_chunk_metadata(structured, chunks, context)[0].metadata

    assert set(metadata) == {
        "schema_version",
        "document",
        "structure",
        "chunk",
        "ingestion",
    }
    assert set(metadata["document"]) == {
        "document_id",
        "document_type",
        "document_number",
        "year",
        "document_title",
        "regulation_status",
        "source_url",
        "source_file",
        "file_hash",
    }
    assert set(metadata["chunk"]) == {
        "chunk_id",
        "parent_chunk_id",
        "chunk_index",
        "content_hash",
        "metadata_hash",
    }


def test_metadata_preserves_complete_legal_hierarchy_and_source() -> None:
    structured, chunks, context = _input()

    enriched = enrich_chunk_metadata(structured, chunks, context)[0]
    document = enriched.metadata["document"]
    structure = enriched.metadata["structure"]

    assert document["document_id"] == "PP-35-2021"
    assert document["document_type"] == "PP"
    assert document["document_number"] == 35
    assert document["year"] == 2021
    assert document["regulation_status"] == "berlaku"
    assert document["source_file"].endswith("PP Nomor 35 Tahun 2021.pdf")
    assert structure["bab"] == "III"
    assert structure["bagian"] == "Kesatu"
    assert structure["paragraf"] == "1"
    assert structure["pasal"] == "15"
    assert structure["page_start"] == structure["page_end"] == 1


def test_metadata_generation_is_deterministic_for_identical_explicit_inputs() -> None:
    structured, chunks, context = _input()

    first = enrich_chunk_metadata(structured, chunks, context)
    second = enrich_chunk_metadata(structured, chunks, context)

    assert first == second
    assert first[0].metadata["chunk"]["metadata_hash"] == metadata_sha256(
        first[0].metadata
    )


def test_content_hash_uses_normalized_chunk_content() -> None:
    assert content_sha256("Pekerja cafe\u0301.\r\n") == content_sha256("Pekerja café.\n")


def test_chunk_from_another_document_is_rejected() -> None:
    structured, chunks, context = _input()
    wrong = replace(chunks[0], document_id="UU-13-2003")

    with pytest.raises(ValueError, match="not PP-35-2021"):
        enrich_chunk_metadata(structured, (wrong,), context)


def test_incorrect_content_hash_is_rejected() -> None:
    structured, chunks, context = _input()
    corrupted = replace(chunks[0], content_hash="0" * 64)

    with pytest.raises(ValueError, match="invalid content hash"):
        enrich_chunk_metadata(structured, (corrupted,), context)


def test_duplicate_chunk_ids_are_rejected_before_storage() -> None:
    structured, chunks, context = _input()

    with pytest.raises(MetadataValidationError, match="duplicate chunk_id"):
        enrich_chunk_metadata(structured, (chunks[0], chunks[0]), context)


def test_missing_parent_chunk_reference_is_rejected() -> None:
    structured, chunks, context = _input()
    child = replace(chunks[0], parent_chunk_id="missing-parent")

    with pytest.raises(MetadataValidationError, match="parent_chunk_id"):
        enrich_chunk_metadata(structured, (child,), context)


def test_invalid_page_range_payload_is_rejected() -> None:
    structured, chunks, context = _input()
    enriched = enrich_chunk_metadata(structured, chunks, context)[0]
    payload = deepcopy(enriched.metadata)
    payload["structure"]["page_start"] = 2
    payload["structure"]["page_end"] = 1
    payload["chunk"]["metadata_hash"] = metadata_sha256(payload)

    with pytest.raises(MetadataValidationError, match="page_start"):
        validate_provenance_payload(
            payload,
            content=enriched.content,
            expected_document_id=structured.document.document_id,
        )


def test_metadata_tampering_breaks_the_integrity_hash() -> None:
    structured, chunks, context = _input()
    enriched = enrich_chunk_metadata(structured, chunks, context)[0]
    payload = deepcopy(enriched.metadata)
    payload["document"]["document_title"] = "Judul yang diubah"

    with pytest.raises(MetadataValidationError, match="metadata_hash"):
        validate_provenance_payload(
            payload,
            content=enriched.content,
            expected_document_id=structured.document.document_id,
        )


def test_invalid_file_hash_is_rejected() -> None:
    structured, chunks, context = _input()
    enriched = enrich_chunk_metadata(structured, chunks, context)[0]
    payload = deepcopy(enriched.metadata)
    payload["document"]["file_hash"] = "not-a-sha256"
    payload["chunk"]["metadata_hash"] = metadata_sha256(payload)

    with pytest.raises(MetadataValidationError, match="file_hash"):
        validate_provenance_payload(
            payload,
            content=enriched.content,
            expected_document_id=structured.document.document_id,
        )


def test_invalid_timestamp_order_is_rejected() -> None:
    structured, chunks, context = _input()
    enriched = enrich_chunk_metadata(structured, chunks, context)[0]
    payload = deepcopy(enriched.metadata)
    payload["ingestion"]["updated_at"] = "2026-09-12T08:30:00+00:00"
    payload["chunk"]["metadata_hash"] = metadata_sha256(payload)

    with pytest.raises(MetadataValidationError, match="updated_at precedes"):
        validate_provenance_payload(
            payload,
            content=enriched.content,
            expected_document_id=structured.document.document_id,
        )


def test_ingestion_versions_and_timestamps_are_explicit() -> None:
    structured, chunks, context = _input()

    ingestion = enrich_chunk_metadata(structured, chunks, context)[0].metadata["ingestion"]

    assert ingestion == {
        "ingestion_version": "v3",
        "parser_version": "kerjapedia-legal-structure-v3",
        "chunker_version": "kerjapedia-structure-aware-chunker-v3",
        "embedding_model": "BAAI/bge-m3@5617a9f",
        "created_at": FIXED_TIME.isoformat(),
        "updated_at": FIXED_TIME.isoformat(),
    }


def test_chunk_table_exposes_forward_provenance_columns() -> None:
    columns = DocumentChunk.__table__.columns

    for name in (
        "parent_chunk_id",
        "chunk_index",
        "legal_node_id",
        "section_path",
        "content_hash",
        "metadata_hash",
        "provenance",
        "created_at",
        "updated_at",
    ):
        assert name in columns


def test_legacy_adapter_dual_writes_categorized_provenance() -> None:
    document = LegacyDocumentMetadata(
        document_id="PP-35-2021",
        title="Peraturan Pemerintah Nomor 35 Tahun 2021",
        short_title="PP 35/2021",
        regulation_type="PP",
        number=35,
        year=2021,
        issuer="Pemerintah Republik Indonesia",
        topics=["PKWT"],
        legal_status="berlaku",
        source_name="JDIH BPK",
        source_url="https://peraturan.bpk.go.id/Details/161904",
        local_file="dataset/PP Nomor 35 Tahun 2021.pdf",
        file_name="PP Nomor 35 Tahun 2021.pdf",
        size_bytes=1024,
        sha256="b" * 64,
        verification_status="verified",
    )
    chunk = LegacyChunk(
        chunk_id="PP-35-2021:pasal-15:0",
        document_id=document.document_id,
        chapter="BAB III",
        section="Bagian Kesatu / Paragraf 1",
        article="Pasal 15",
        paragraph="Ayat (1)",
        page_start=12,
        page_end=13,
        text="Pasal 15\n(1) Pengusaha wajib memberikan kompensasi.",
        token_count=9,
        topics=["PKWT"],
        legal_status="berlaku",
        source_url=document.source_url,
    )

    payload = build_legacy_chunk_provenance(
        document,
        chunk,
        chunk_index=4,
        ingestion_version="v2",
        parser_version="legacy-parser-v2",
        chunker_version="legacy-chunker-v2",
        embedding_model="BAAI/bge-m3",
        created_at=FIXED_TIME,
        updated_at=FIXED_TIME,
    )

    assert payload["structure"] == {
        "bab": "III",
        "bagian": "Kesatu",
        "paragraf": "1",
        "pasal": "15",
        "ayat": "1",
        "page_start": 12,
        "page_end": 13,
        "section_path": [
            "BAB III",
            "Bagian Kesatu",
            "Paragraf 1",
            "Pasal 15",
            "Ayat (1)",
        ],
        "legal_node_id": None,
        "amendment_scope": None,
    }
    assert payload["chunk"]["chunk_index"] == 4
    assert payload["chunk"]["content_hash"] == content_sha256(chunk.text)
