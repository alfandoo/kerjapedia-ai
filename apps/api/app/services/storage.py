"""Supabase Storage — object/file storage only.

Data ownership:
- Neon PostgreSQL = relational system of record (metadata, governance, jobs).
- Supabase Storage = file/artifact source of truth (PDF, OCR, chunks.jsonl, logs).
- Supabase PostgreSQL is NOT used; do not treat Supabase as a second database.

Bucket ``regulations`` is private. Never expose private objects via a manually
built ``/object/public/`` URL. Use signed URLs with a short TTL for downloads.
Regulation artifacts live under ``regulations/`` and ``uploads/``; temporary
CV files (if any) must live under ``cv-tmp/`` with a retention TTL and must
never be indexed into the regulation Upstash namespace.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.services.supabase import get_supabase

BUCKET = settings.supabase_storage_bucket

# Storage prefixes — keep regulation and transient CV data separated.
REGULATION_PREFIX = "regulations/"
UPLOAD_PREFIX = "uploads/"
CV_TMP_PREFIX = "cv-tmp/"
CV_RETENTION_SECONDS = 24 * 3600


def ensure_bucket() -> None:
    supabase = get_supabase()
    buckets = supabase.storage.list_buckets()
    if not any(b.name == BUCKET for b in buckets):
        supabase.storage.create_bucket(BUCKET, options={"public": False})


def _storage_path_or_key(storage_path: str) -> str:
    # Return the internal storage path (not a public URL) so callers cannot
    # accidentally treat a private object as publicly reachable.
    return storage_path


def upload_pdf(
    local_path: Path,
    storage_path: str,
    file_name: str,
) -> str:
    ensure_bucket()
    supabase = get_supabase()
    content = local_path.read_bytes()
    supabase.storage.from_(BUCKET).upload(
        path=storage_path,
        file=content,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )
    return _storage_path_or_key(storage_path)


def upload_bytes(
    content: bytes,
    storage_path: str,
    content_type: str = "application/pdf",
) -> str:
    ensure_bucket()
    supabase = get_supabase()
    supabase.storage.from_(BUCKET).upload(
        path=storage_path,
        file=content,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return _storage_path_or_key(storage_path)


def create_signed_url(storage_path: str, expires_in_seconds: int = 3600) -> str:
    """Create a short-lived signed URL for a private object."""
    supabase = get_supabase()
    result = supabase.storage.from_(BUCKET).create_signed_url(
        storage_path, expires_in_seconds
    )
    if isinstance(result, dict):
        signed = result.get("signedURL") or result.get("signedUrl") or result.get("url")
        if signed:
            return str(signed)
    url = getattr(result, "signed_url", None) or getattr(result, "signedURL", None)
    if url:
        return str(url)
    raise RuntimeError("Supabase signed URL creation failed.")


def get_public_url(storage_path: str) -> str:
    """Legacy helper kept for explicitly public assets only.

    The ``regulations`` bucket is private; prefer :func:`create_signed_url`
    for downloads. This helper is retained for backward compatibility and
    should not be used for private regulation or CV artifacts.
    """
    supabase = get_supabase()
    return supabase.storage.from_(BUCKET).get_public_url(storage_path)


def delete_file(storage_path: str) -> None:
    supabase = get_supabase()
    supabase.storage.from_(BUCKET).remove([storage_path])
