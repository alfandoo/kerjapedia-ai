from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import asdict, dataclass
from importlib import metadata
from typing import Any

PIPELINE_VERSION = "kerjapedia-ingestion-v2"
PARSER_VERSION = "kerjapedia-legal-parser-v2"
CHUNKER_VERSION = "kerjapedia-legal-chunker-v2"
OCR_PROFILE_VERSION = "ocrmypdf-ind-eng-v1"
DEFAULT_BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"


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
    ocr_jobs: int = 2
    embedding_model: str = "BAAI/bge-m3"
    embedding_revision: str = DEFAULT_BGE_M3_REVISION
    embedding_dimension: int = 1024
    require_native_sparse: bool = True
    runtime: dict[str, str] | None = None

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
    config: IngestionBuildConfig


def make_build_identity(
    document_id: str,
    source_sha256: str,
    config: IngestionBuildConfig,
) -> BuildIdentity:
    digest = hashlib.sha256(
        f"{document_id}:{source_sha256}:{config.config_hash}".encode()
    ).hexdigest()
    return BuildIdentity(
        build_id=f"ingb_{digest[:32]}",
        config_hash=config.config_hash,
        config=config,
    )


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
    *,
    release_candidate: bool = False,
) -> IngestionBuildConfig:
    return IngestionBuildConfig(
        target_tokens=int(settings.ingestion_target_tokens),
        max_tokens=int(settings.ingestion_max_tokens),
        overlap_tokens=int(settings.ingestion_overlap_tokens),
        min_merge_tokens=int(settings.ingestion_min_merge_tokens),
        parent_tokens=int(settings.ingestion_parent_tokens),
        embedding_batch_size=int(settings.ingestion_embedding_batch_size),
        ocr_jobs=max(1, min(int(settings.ingestion_ocr_jobs), 2)),
        embedding_model=str(provider.model_name),
        embedding_revision=provider_revision(provider),
        embedding_dimension=int(getattr(provider, "dimensions", settings.embedding_dimension)),
        require_native_sparse=(
            release_candidate or bool(getattr(provider, "require_native_sparse", False))
        ),
        runtime=runtime_provenance(),
    )


def validate_candidate_runtime(config: IngestionBuildConfig) -> None:
    if config.embedding_model.lower() != "baai/bge-m3":
        raise RuntimeError("Release-candidate ingestion requires BAAI/bge-m3.")
    if config.embedding_revision in {"", "main", "unversioned", "provider-managed"}:
        raise RuntimeError("Release-candidate ingestion requires a pinned embedding revision.")
    missing = [
        name
        for name in ("ocrmypdf", "flagembedding", "tesseract", "qpdf", "ghostscript")
        if (config.runtime or {}).get(name, "unavailable") == "unavailable"
    ]
    if missing:
        raise RuntimeError("Release-candidate ingestion runtime is missing: " + ", ".join(missing))
    if not config.require_native_sparse:
        raise RuntimeError("Release-candidate ingestion requires native sparse embeddings.")
