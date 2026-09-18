from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import asdict, dataclass
from importlib import metadata
from typing import Any

PIPELINE_VERSION = "kerjapedia-ingestion-v15-amendment-provenance"
PARSER_VERSION = "kerjapedia-legal-parser-v10"
CHUNKER_VERSION = "kerjapedia-legal-chunker-v6"
OCR_PROFILE_VERSION = "ocrmypdf-page-fallback-v2"
BUILD_IDENTITY_SCHEMA_VERSION = "build-identity-v2"
MAX_EMBEDDING_BATCH_SIZE = 64


@dataclass(frozen=True)
class IngestionBuildConfig:
    pipeline_version: str = PIPELINE_VERSION
    parser_version: str = PARSER_VERSION
    chunker_version: str = CHUNKER_VERSION
    ocr_profile: str = OCR_PROFILE_VERSION
    target_tokens: int = 350
    max_tokens: int = 550
    overlap_tokens: int = 60
    min_merge_tokens: int = 180
    parent_tokens: int = 1200
    embedding_batch_size: int = 16
    embedding_timeout_seconds: float = 120.0
    embedding_max_retries: int = 3
    embedding_retry_initial_seconds: float = 1.0
    ocr_jobs: int = 2
    embedding_model: str = "local-hash-embedding-v1"
    embedding_revision: str = "deterministic-v1"
    embedding_dimension: int = 64
    require_native_sparse: bool = False
    evaluation_thresholds: dict[str, int | float] | None = None
    runtime: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.embedding_batch_size <= MAX_EMBEDDING_BATCH_SIZE:
            raise ValueError(
                f"embedding_batch_size must be between 1 and "
                f"{MAX_EMBEDDING_BATCH_SIZE}"
            )
        if self.embedding_timeout_seconds <= 0:
            raise ValueError("embedding_timeout_seconds must be positive")
        if self.embedding_max_retries < 0:
            raise ValueError("embedding_max_retries must not be negative")
        if self.embedding_retry_initial_seconds < 0:
            raise ValueError("embedding_retry_initial_seconds must not be negative")
        if self.embedding_dimension < 1:
            raise ValueError("embedding_dimension must be positive")

    def payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["runtime"] = dict(sorted((self.runtime or {}).items()))
        return payload

    @property
    def config_hash(self) -> str:
        canonical = json.dumps(
            self.payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BuildIdentity:
    build_id: str
    config_hash: str
    metadata_hash: str
    config: IngestionBuildConfig


def make_build_identity(
    document_id: str,
    source_sha256: str,
    config: IngestionBuildConfig,
    metadata_hash: str | None = None,
) -> BuildIdentity:
    resolved_metadata_hash = metadata_hash or hashlib.sha256(b"unscoped").hexdigest()
    digest = hashlib.sha256(
        ":".join(
            (
                BUILD_IDENTITY_SCHEMA_VERSION,
                document_id,
                source_sha256,
                resolved_metadata_hash,
                config.config_hash,
            )
        ).encode()
    ).hexdigest()
    return BuildIdentity(
        build_id=f"ingb_{digest[:32]}",
        config_hash=config.config_hash,
        metadata_hash=resolved_metadata_hash,
        config=config,
    )


def document_metadata_hash(document: Any) -> str:
    """Hash retrieval-relevant source metadata using a canonical representation."""
    payload = {
        "document_id": str(document.document_id),
        "title": str(document.title),
        "short_title": str(document.short_title),
        "regulation_type": str(document.regulation_type),
        "number": int(document.number),
        "year": int(document.year),
        "issuer": str(document.issuer),
        "topics": sorted(str(topic) for topic in document.topics),
        "legal_status": str(document.legal_status),
        "source_name": str(document.source_name),
        "source_url": str(document.source_url),
        "local_file": str(document.local_file),
        "file_name": str(document.file_name),
        "size_bytes": int(document.size_bytes),
        "sha256": str(document.sha256),
        "verification_status": str(document.verification_status),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def provider_revision(provider: object) -> str:
    return str(getattr(provider, "model_revision", "unversioned"))


def runtime_provenance() -> dict[str, str]:
    packages = {
        "python": platform.python_version(),
        "pymupdf": _package_version("PyMuPDF"),
        "ocrmypdf": _package_version("ocrmypdf"),
        "flagembedding": _package_version("FlagEmbedding"),
        "sentence-transformers": _package_version("sentence-transformers"),
    }
    packages["tesseract"] = _command_version(["tesseract", "--version"])
    packages["qpdf"] = _command_version(["qpdf", "--version"])
    packages["ghostscript"] = _command_version(["gs", "--version"])
    return packages


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unavailable"


def _command_version(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return "unavailable"
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0][:160] if output else "unavailable"


def build_config_from_settings(
    settings: Any,
    provider: object,
) -> IngestionBuildConfig:
    return IngestionBuildConfig(
        target_tokens=int(settings.ingestion_target_tokens),
        max_tokens=int(settings.ingestion_max_tokens),
        overlap_tokens=int(settings.ingestion_overlap_tokens),
        min_merge_tokens=int(settings.ingestion_min_merge_tokens),
        parent_tokens=int(settings.ingestion_parent_tokens),
        embedding_batch_size=int(settings.ingestion_embedding_batch_size),
        embedding_timeout_seconds=float(settings.ingestion_embedding_timeout_seconds),
        embedding_max_retries=int(settings.ingestion_embedding_max_retries),
        embedding_retry_initial_seconds=float(
            settings.ingestion_embedding_retry_initial_seconds
        ),
        ocr_jobs=max(1, min(int(settings.ingestion_ocr_jobs), 2)),
        embedding_model=str(provider.model_name),
        embedding_revision=provider_revision(provider),
        embedding_dimension=int(getattr(provider, "dimensions", 64)),
        require_native_sparse=bool(getattr(provider, "require_native_sparse", False)),
        runtime=runtime_provenance(),
    )
