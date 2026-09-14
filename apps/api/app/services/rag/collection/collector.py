"""Collect files into records: validate, quarantine, track checksums.

Eligibility answers "may this file enter the pipeline?" without ever
crashing it: unfit files come back quarantined with reasons. Zero-text
(scanned) PDFs stay eligible — OCR downstream handles them.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from app.services.rag.collection.schemas import (
    ChecksumEvent,
    CollectedDocument,
    EligibilityIssue,
    EligibilityVerdict,
)

PDF_MAGIC = b"%PDF-"
_MIN_TEXT_CHARS = 40


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _probe_pdf(path: Path) -> tuple[int, bool, int]:
    """Return (page_count, encrypted, extractable_chars) for a PDF file."""
    import fitz

    pages, chars = 0, 0
    with fitz.open(path) as document:
        if document.needs_pass:
            return 0, True, 0
        pages = document.page_count
        for page in document:
            chars += len(page.get_text("text").strip())
            if chars >= _MIN_TEXT_CHARS:
                break
    return pages, False, chars


def check_eligibility(path: Path) -> EligibilityVerdict:
    """Inspect a file; quarantine with reasons instead of raising."""
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pdf":
        issue = EligibilityIssue(
            code="not_a_pdf",
            message=f"Expected PDF extension: {path.name}",
        )
        return EligibilityVerdict(eligible=False, issues=(issue,), quarantined=True)
    with path.open("rb") as file:
        if file.read(len(PDF_MAGIC)) != PDF_MAGIC:
            issue = EligibilityIssue(
                code="bad_magic",
                message=f"File does not start with PDF header: {path.name}",
            )
            return EligibilityVerdict(eligible=False, issues=(issue,), quarantined=True)
    if path.stat().st_size == 0:
        issue = EligibilityIssue(
            code="empty_file", message=f"File is empty: {path.name}"
        )
        return EligibilityVerdict(eligible=False, issues=(issue,), quarantined=True)

    page_count, encrypted, chars = _probe_pdf(path)
    if encrypted:
        issue = EligibilityIssue(
            code="encrypted",
            message=f"PDF requires a password: {path.name}",
        )
        return EligibilityVerdict(eligible=False, issues=(issue,), quarantined=True)
    if page_count == 0:
        issue = EligibilityIssue(
            code="no_pages", message=f"PDF has no pages: {path.name}"
        )
        return EligibilityVerdict(eligible=False, issues=(issue,), quarantined=True)
    if chars < _MIN_TEXT_CHARS:
        issue = EligibilityIssue(
            code="no_embedded_text",
            message="No embedded text layer; routed to OCR downstream.",
            fatal=False,
        )
        return EligibilityVerdict(eligible=True, issues=(issue,))
    return EligibilityVerdict(eligible=True)


def collect_document(
    path: Path,
    *,
    document_id: str,
    title: str,
    source_id: str,
    source_url: str = "",
    origin: str = "curated",
    regulation_type: str = "",
    number: int = 0,
    year: int = 0,
    issuer: str = "",
    collected_at: datetime | None = None,
) -> tuple[CollectedDocument, EligibilityVerdict]:
    """Build a collection record for a file plus its eligibility verdict."""
    import hashlib

    verdict = check_eligibility(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    size = path.stat().st_size
    now = collected_at or _utcnow()
    page_count = 0
    if verdict.eligible:
        try:
            page_count, _, _ = _probe_pdf(path)
        except Exception:  # Probing must not break collection.
            page_count = 0
    document = CollectedDocument(
        document_id=document_id,
        title=title,
        regulation_type=regulation_type,
        number=number,
        year=year,
        issuer=issuer,
        source_id=source_id,
        source_url=source_url,
        local_file=path.as_posix(),
        file_name=path.name,
        size_bytes=size,
        sha256=digest,
        checksum_history=(
            ChecksumEvent(
                sha256=digest, size_bytes=size, collected_at=now, origin=origin
            ),
        ),
        collected_at=now,
        origin=origin,
        page_count=page_count,
    )
    return document, verdict


def register_checksum(
    document: CollectedDocument,
    sha256: str,
    size_bytes: int,
    origin: str,
    collected_at: datetime | None = None,
) -> CollectedDocument:
    """Append a checksum observation; history is never rewritten."""
    event = ChecksumEvent(
        sha256=sha256,
        size_bytes=size_bytes,
        collected_at=collected_at or _utcnow(),
        origin=origin,
    )
    return replace(
        document,
        sha256=sha256,
        size_bytes=size_bytes,
        checksum_history=(*document.checksum_history, event),
    )
