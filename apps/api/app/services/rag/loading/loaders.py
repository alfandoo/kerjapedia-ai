"""Typed loaders and safe on-disk layout.

Every source kind (local file today; DOCX, web, database tomorrow) speaks
through the :class:`Loader` protocol and lands in a deterministic,
traversal-proof directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

SOURCE_FILE_NAME = "source.pdf"

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class LoadedFile:
    """Bytes on disk plus intake metadata. Content already validated."""

    path: Path
    file_name: str
    size_bytes: int
    sha256: str
    origin: str  # curated | upload | connector


class Loader(Protocol):
    """A source of document bytes. Implementations never trust input."""

    @property
    def origin(self) -> str: ...

    def load(self, reference: str, content: bytes | None = None) -> LoadedFile: ...


def sanitize_identifier(value: str, field: str = "document_id") -> str:
    """Refuse identifiers that could escape the store layout."""
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid {field}: {value!r}")
    if value in {".", ".."}:
        raise ValueError(f"Invalid {field}: {value!r}")
    return value


def sanitize_file_name(value: str) -> str:
    """Strip directories and unsafe characters from user-supplied names."""
    name = Path(value).name.strip().strip(".")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    stem, dot, suffix = cleaned.rpartition(".")
    if not stem or not suffix:
        raise ValueError(f"Invalid file name: {value!r}")
    return cleaned


def store_layout_for(store_root: Path, origin: str, document_id: str) -> Path:
    """Deterministic directory: <store>/<origin>/<document_id>/."""
    sanitize_identifier(document_id)
    if origin not in {"curated", "upload", "connector"}:
        raise ValueError(f"Unknown origin: {origin!r}")
    return store_root / origin / document_id


class LocalFileLoader:
    """Load an already-on-disk file (curated dataset). Read-only."""

    origin = "curated"

    def load(self, reference: str, content: bytes | None = None) -> LoadedFile:
        import hashlib

        path = Path(reference)
        raw = path.read_bytes()
        return LoadedFile(
            path=path,
            file_name=path.name,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            origin=self.origin,
        )


class BytesLoader:
    """Store uploaded/fetched bytes atomically under the store layout."""

    def __init__(self, store_root: Path, origin: str) -> None:
        if origin not in {"upload", "connector"}:
            raise ValueError(f"BytesLoader origin must be upload/connector: {origin!r}")
        self._store_root = store_root
        self.origin = origin

    def load(self, reference: str, content: bytes | None = None) -> LoadedFile:
        import hashlib
        import tempfile

        if content is None:
            raise ValueError("BytesLoader requires content bytes.")
        document_id = sanitize_identifier(reference)
        directory = store_layout_for(self._store_root, self.origin, document_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / SOURCE_FILE_NAME
        handle, temp_path = tempfile.mkstemp(
            prefix=".source.", suffix=".tmp", dir=directory
        )
        try:
            with open(handle, "wb") as file:
                file.write(content)
            Path(temp_path).replace(target)
        except BaseException:
            Path(temp_path).unlink(missing_ok=True)
            raise
        return LoadedFile(
            path=target,
            file_name=SOURCE_FILE_NAME,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            origin=self.origin,
        )
