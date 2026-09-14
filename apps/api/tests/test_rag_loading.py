from datetime import UTC, datetime
from pathlib import Path

import fitz
import pytest

from app.services.rag.collection.sources import FetchedFile
from app.services.rag.loading import (
    MAX_UPLOAD_BYTES,
    intake_connector_file,
    intake_local_file,
    intake_upload,
    sanitize_file_name,
    sanitize_identifier,
    store_layout_for,
)


def make_pdf_bytes(text: str = "Pasal 1 Ketentuan umum.") -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    raw = document.tobytes()
    document.close()
    return raw


def test_intake_local_file_registers_curated_record(tmp_path: Path) -> None:
    pdf = tmp_path / "pp.pdf"
    pdf.write_bytes(make_pdf_bytes())

    document, verdict = intake_local_file(
        pdf, document_id="PP-1-2020", title="PP 1/2020", source_id="bpk"
    )

    assert verdict.eligible is True
    assert document.origin == "curated"
    assert document.local_file == pdf.as_posix()


def test_intake_upload_validates_at_intake_not_later(tmp_path: Path) -> None:
    document, verdict = intake_upload(
        make_pdf_bytes(),
        store_root=tmp_path,
        document_id="DOC-1",
        title="Doc",
        file_name="doc.pdf",
        source_id="bpk",
    )

    assert verdict.eligible is True
    assert document.origin == "upload"
    assert (tmp_path / "upload" / "DOC-1" / "source.pdf").exists()


def test_intake_upload_rejects_bad_bytes_immediately(tmp_path: Path) -> None:
    document, verdict = intake_upload(
        b"not a pdf at all",
        store_root=tmp_path,
        document_id="DOC-2",
        title="Doc",
        file_name="doc.pdf",
        source_id="bpk",
    )

    assert verdict.eligible is False
    assert verdict.quarantined is True


def test_intake_upload_enforces_size_cap(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exceeds"):
        intake_upload(
            b"%PDF-" + b"x" * (MAX_UPLOAD_BYTES + 1),
            store_root=tmp_path,
            document_id="DOC-3",
            title="Doc",
            file_name="doc.pdf",
            source_id="bpk",
        )


def test_intake_connector_file_records_origin_and_url(tmp_path: Path) -> None:
    fetched = FetchedFile(
        file_name="pp.pdf",
        content=make_pdf_bytes(),
        source_url="https://peraturan.bpk.go.id/Details/1",
        fetched_at=datetime.now(UTC),
    )

    document, verdict = intake_connector_file(
        fetched,
        store_root=tmp_path,
        registry_source_id="bpk",
        document_id="PP-2-2021",
        title="PP 2/2021",
    )

    assert verdict.eligible is True
    assert document.origin == "connector"
    assert document.source_url == "https://peraturan.bpk.go.id/Details/1"
    assert document.checksum_history[0].origin == "connector"


def test_identifiers_reject_path_traversal() -> None:
    with pytest.raises(ValueError, match="Invalid document_id"):
        sanitize_identifier("../../etc")
    with pytest.raises(ValueError, match="Invalid file name"):
        sanitize_file_name("../../etc/passwd")
    assert sanitize_file_name("Kemnaker No. 6 Tahun 2016.pdf") == "Kemnaker_No._6_Tahun_2016.pdf"


def test_store_layout_is_deterministic_per_origin(tmp_path: Path) -> None:
    assert store_layout_for(tmp_path, "upload", "DOC-1") == tmp_path / "upload" / "DOC-1"
    with pytest.raises(ValueError, match="Unknown origin"):
        store_layout_for(tmp_path, "p2p", "DOC-1")
