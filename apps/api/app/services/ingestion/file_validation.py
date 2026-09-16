from __future__ import annotations

import hashlib
from pathlib import Path

from app.services.ingestion.metadata import duplicate_ids_by_checksum
from app.services.ingestion.schemas import DocumentMetadata, FileValidationResult

PDF_MAGIC = b"%PDF-"

# P3-1: Consistent resource limits for curated and uploaded PDFs
MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MIN_PDF_SIZE_BYTES = 1024  # 1 KB
MAX_PDF_PAGES = 500
MIN_PDF_PAGES = 1
MAX_TOTAL_TOKENS = 500_000
MIN_TOTAL_TOKENS = 100


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def has_pdf_header(path: Path) -> bool:
    with path.open("rb") as file:
        return file.read(len(PDF_MAGIC)) == PDF_MAGIC


def validate_pdf_resources(
    path: Path,
    page_count: int,
    estimated_tokens: int,
) -> list[str]:
    """Validate PDF resource limits and return warnings/errors."""
    warnings = []
    size_bytes = path.stat().st_size

    # Size limits
    if size_bytes > MAX_PDF_SIZE_BYTES:
        warnings.append(
            f"PDF size ({size_bytes / (1024 * 1024):.1f} MB) exceeds maximum "
            f"({MAX_PDF_SIZE_BYTES / (1024 * 1024):.0f} MB)"
        )
    elif size_bytes < MIN_PDF_SIZE_BYTES:
        warnings.append(
            f"PDF size ({size_bytes} bytes) below minimum ({MIN_PDF_SIZE_BYTES} bytes)"
        )

    # Page limits
    if page_count > MAX_PDF_PAGES:
        warnings.append(
            f"PDF page count ({page_count}) exceeds maximum ({MAX_PDF_PAGES})"
        )
    elif page_count < MIN_PDF_PAGES:
        warnings.append(
            f"PDF page count ({page_count}) below minimum ({MIN_PDF_PAGES})"
        )

    # Token limits
    if estimated_tokens > MAX_TOTAL_TOKENS:
        warnings.append(
            f"Estimated tokens ({estimated_tokens}) exceeds maximum ({MAX_TOTAL_TOKENS})"
        )
    elif estimated_tokens < MIN_TOTAL_TOKENS:
        warnings.append(
            f"Estimated tokens ({estimated_tokens}) below minimum ({MIN_TOTAL_TOKENS})"
        )

    return warnings


def validate_pdf_file(
    path: Path,
    document: DocumentMetadata,
    all_documents: list[DocumentMetadata],
    *,
    page_count: int | None = None,
    estimated_tokens: int | None = None,
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

    # P3-1: Validate resource limits if page count provided
    resource_warnings = []
    if page_count is not None:
        resource_warnings = validate_pdf_resources(
            path,
            page_count=page_count,
            estimated_tokens=estimated_tokens or 0,
        )

    # Raise if critical resource limits exceeded
    for warning in resource_warnings:
        if "exceeds maximum" in warning:
            raise ValueError(warning)

    return FileValidationResult(
        path=path,
        is_pdf=is_pdf,
        size_bytes=size_bytes,
        sha256=sha256,
        duplicate_document_ids=duplicates,
    )
