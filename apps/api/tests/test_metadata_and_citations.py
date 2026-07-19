import json

import pytest

from app.services.answering.citations import build_citations, compact_text
from app.services.ingestion.metadata import (
    duplicate_ids_by_checksum,
    find_document,
    load_manifest,
)
from app.services.retrieval.schemas import RankedChunk, RetrievalDocument


def metadata_payload(document_id: str, sha256: str = "a" * 64) -> dict:
    return {
        "document_id": document_id,
        "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
        "short_title": "PP 35/2021",
        "regulation_type": "PP",
        "number": 35,
        "year": 2021,
        "issuer": "Pemerintah Republik Indonesia",
        "topics": ["pkwt"],
        "legal_status": "active",
        "source_name": "JDIH BPK",
        "source_url": "https://peraturan.bpk.go.id/",
        "local_file": "dataset/PP-35-2021.pdf",
        "file_name": "PP-35-2021.pdf",
        "size_bytes": 100,
        "sha256": sha256,
        "verification_status": "verified",
    }


def test_metadata_manifest_loads_and_detects_duplicate_checksum(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    metadata_payload("PP-35-2021"),
                    metadata_payload("PP-36-2021"),
                ]
            }
        ),
        encoding="utf-8",
    )

    documents = load_manifest(manifest)["documents"]

    assert find_document(documents, "PP-35-2021").year == 2021
    assert duplicate_ids_by_checksum(documents, "a" * 64, "PP-35-2021") == ["PP-36-2021"]
    with pytest.raises(ValueError, match="Document not found"):
        find_document(documents, "UNKNOWN")


def test_citation_formatter_compacts_text_and_deduplicates_chunks() -> None:
    document = RetrievalDocument(
        chunk_id="chunk-1",
        document_id="PP-35-2021",
        text="  Pasal 15\n pekerja PKWT berhak memperoleh uang kompensasi.  ",
        chapter="BAB II",
        section="PKWT",
        article="Pasal 15",
        paragraph="Ayat (1)",
        page_start=12,
        page_end=12,
        token_count=9,
        topics=["pkwt"],
        legal_status="active",
        source_url="https://peraturan.bpk.go.id/",
        metadata={"title": "PP Nomor 35 Tahun 2021", "short_title": "PP 35/2021"},
    )
    ranked = RankedChunk(
        document=document,
        lexical_score=1.0,
        semantic_score=0.9,
        fusion_score=0.8,
        rerank_score=0.7,
        final_score=0.75,
        match_reasons=["topic:pkwt"],
    )

    citations = build_citations([ranked, ranked])

    assert len(citations) == 1
    assert citations[0].citation_id == "cit_001"
    assert citations[0].article == "Pasal 15"
    assert citations[0].quote == "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi."
    assert compact_text("kata " * 20, limit=20).endswith("...")
