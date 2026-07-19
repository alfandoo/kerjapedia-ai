from __future__ import annotations

import hashlib
from pathlib import Path

from app.services.ingestion.metadata import duplicate_ids_by_checksum
from app.services.ingestion.schemas import DocumentMetadata, FileValidationResult

PDF_MAGIC = b"%PDF-"


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def has_pdf_header(path: Path) -> bool:
    with path.open("rb") as file:
        return file.read(len(PDF_MAGIC)) == PDF_MAGIC


def validate_pdf_file(
    path: Path,
    document: DocumentMetadata,
    all_documents: list[DocumentMetadata],
) -> FileValidationResult:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected PDF extension: {path}")

    size_bytes = path.stat().st_size
    sha256 = compute_sha256(path)
    is_pdf = has_pdf_header(path)
    duplicates = duplicate_ids_by_checksum(all_documents, sha256, document.document_id)

    if not is_pdf:
        raise ValueError(f"File does not start with PDF header: {path}")
    if size_bytes != document.size_bytes:
        raise ValueError(
            f"Size mismatch for {document.document_id}: expected "
            f"{document.size_bytes}, got {size_bytes}"
        )
    if sha256 != document.sha256:
        raise ValueError(
            f"Checksum mismatch for {document.document_id}: expected "
            f"{document.sha256}, got {sha256}"
        )

    return FileValidationResult(
        path=path,
        is_pdf=is_pdf,
        size_bytes=size_bytes,
        sha256=sha256,
        duplicate_document_ids=duplicates,
    )
