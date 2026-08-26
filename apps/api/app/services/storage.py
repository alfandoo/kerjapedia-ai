from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.services.supabase import get_supabase

BUCKET = settings.supabase_storage_bucket


def ensure_bucket() -> None:
    supabase = get_supabase()
    buckets = supabase.storage.list_buckets()
    if not any(b.name == BUCKET for b in buckets):
        supabase.storage.create_bucket(BUCKET, options={"public": False})


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
    return f"{settings.supabase_url}/storage/v1/object/public/{BUCKET}/{storage_path}"


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
    return f"{settings.supabase_url}/storage/v1/object/public/{BUCKET}/{storage_path}"


def get_public_url(storage_path: str) -> str:
    supabase = get_supabase()
    return supabase.storage.from_(BUCKET).get_public_url(storage_path)


def delete_file(storage_path: str) -> None:
    supabase = get_supabase()
    supabase.storage.from_(BUCKET).remove([storage_path])
