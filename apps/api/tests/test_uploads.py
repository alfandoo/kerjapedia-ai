import hashlib
import tempfile
from pathlib import Path

from app.services.ingestion.schemas import DocumentMetadata
from app.services.ingestion.uploads import (
    load_uploads_manifest,
    merge_documents,
    register_upload,
    uploads_manifest_path,
)


def _make_storage_root() -> Path:
    temp_dir = Path(tempfile.mkdtemp())
    return temp_dir / "storage" / "ingestion"


def _pdf_bytes() -> bytes:
    return b"%PDF-1.7\n%%EOF\n"


def test_register_upload_writes_source_and_manifest() -> None:
    storage_root = _make_storage_root()

    document = register_upload(
        storage_root,
        document_id="PP-51-2023",
        file_name="PP Nomor 51 Tahun 2023.pdf",
        topic="pengupahan",
        content=_pdf_bytes(),
        source_url="https://storage.example/uploads/PP-51-2023.pdf",
    )

    source_file = storage_root / "uploads" / "PP-51-2023" / "source.pdf"
    assert source_file.exists()
    assert source_file.read_bytes() == _pdf_bytes()
    assert uploads_manifest_path(storage_root).exists()

    assert document.document_id == "PP-51-2023"
    assert document.regulation_type == "PP"
    assert document.number == 51
    assert document.year == 2023
    assert document.topics == ["pengupahan", "thr"]
    assert document.sha256 == hashlib.sha256(_pdf_bytes()).hexdigest()
    assert document.size_bytes == len(_pdf_bytes())
    assert document.local_file.replace("\\", "/").endswith(
        "storage/ingestion/uploads/PP-51-2023/source.pdf"
    )

    loaded = load_uploads_manifest(storage_root)
    assert [item.document_id for item in loaded] == ["PP-51-2023"]
    assert isinstance(loaded[0], DocumentMetadata)


def test_register_upload_upserts_existing_document_id() -> None:
    storage_root = _make_storage_root()
    first = register_upload(
        storage_root,
        document_id="UU-6-2023",
        file_name="UU Nomor 6 Tahun 2023.pdf",
        topic="pkwt",
        content=_pdf_bytes(),
        source_url="https://storage.example/first.pdf",
    )
    second = register_upload(
        storage_root,
        document_id="UU-6-2023",
        file_name="UU Nomor 6 Tahun 2023 Baru.pdf",
        topic="pkwt",
        content=b"%PDF-1.7\n%%EOF\nupdated\n",
        source_url="https://storage.example/second.pdf",
    )

    loaded = load_uploads_manifest(storage_root)
    assert len(loaded) == 1
    assert loaded[0].sha256 != first.sha256
    assert loaded[0].sha256 == second.sha256


def test_load_uploads_manifest_missing_returns_empty() -> None:
    storage_root = _make_storage_root()
    assert load_uploads_manifest(storage_root) == []


def test_merge_documents_uploads_override_dataset() -> None:
    dataset = [
        DocumentMetadata.from_dict(
            {
                "document_id": "UU-13-2003",
                "title": "UU 13/2003",
                "short_title": "UU 13/2003",
                "regulation_type": "UU",
                "number": 13,
                "year": 2003,
                "issuer": "Pemerintah",
                "topics": ["dasar_ketenagakerjaan"],
                "legal_status": "active",
                "source_name": "BPK",
                "source_url": "https://peraturan.bpk.go.id/",
                "local_file": "dataset/UU-13-2003.pdf",
                "file_name": "UU-13-2003.pdf",
                "size_bytes": 1,
                "sha256": "a" * 64,
                "verification_status": "verified",
            }
        )
    ]
    uploads = [
        DocumentMetadata.from_dict(
            {
                "document_id": "UU-13-2003",
                "title": "UU 13/2003 Revisi",
                "short_title": "UU 13/2003",
                "regulation_type": "UU",
                "number": 13,
                "year": 2003,
                "issuer": "Pemerintah",
                "topics": ["dasar_ketenagakerjaan"],
                "legal_status": "needs_verification",
                "source_name": "Upload Admin",
                "source_url": "https://storage.example/uu-13-2003.pdf",
                "local_file": "storage/ingestion/uploads/UU-13-2003/source.pdf",
                "file_name": "UU-13-2003.pdf",
                "size_bytes": 2,
                "sha256": "b" * 64,
                "verification_status": "pending_detail_url",
            }
        )
    ]

    merged = merge_documents(dataset, uploads)

    assert len(merged) == 1
    assert merged[0].source_name == "Upload Admin"
    assert merged[0].sha256 == "b" * 64
