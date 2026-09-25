"""CV upload validation and storage-prefix helpers."""

from __future__ import annotations

from pathlib import Path

CV_TMP_PREFIX = "cv-tmp/"
CV_MAX_BYTES = 5 * 1024 * 1024
_ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt"}
_ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


def validate_cv_upload(file_name: str, content_type: str, size_bytes: int) -> str:
    """Validate a CV upload; return a safe storage key prefix on success."""
    if ".." in file_name or "/" in file_name or "\\" in file_name:
        raise ValueError("Invalid CV file name.")
    safe_name = Path(file_name).name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise ValueError("CV must be PDF, DOCX, or TXT.")
    if content_type not in _ALLOWED_MIME:
        raise ValueError("Unsupported CV content type.")
    if size_bytes <= 0 or size_bytes > CV_MAX_BYTES:
        raise ValueError("CV size out of bounds.")
    return f"{CV_TMP_PREFIX}<session>/{safe_name}"
