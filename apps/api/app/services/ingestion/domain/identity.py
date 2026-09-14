"""Canonical content identity helpers shared by ingestion stages."""

from __future__ import annotations

import hashlib
import unicodedata


def normalize_chunk_content(content: str) -> str:
    """Canonicalize representation without rewriting legal text."""
    normalized = unicodedata.normalize("NFC", content)
    return normalized.replace("\r\n", "\n").replace("\r", "\n").strip()


def content_sha256(content: str) -> str:
    return hashlib.sha256(normalize_chunk_content(content).encode("utf-8")).hexdigest()
