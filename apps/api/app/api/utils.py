from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings
from app.services.ingestion.metadata import find_document, load_manifest
from app.services.ingestion.uploads import load_uploads_manifest, merge_documents


def project_root() -> Path:
    return settings.project_root or Path(__file__).resolve().parents[4]


def dataset_metadata_path() -> Path:
    return project_root() / "dataset" / "metadata.json"


def storage_root() -> Path:
    return project_root() / "storage" / "ingestion"


def load_dataset_documents() -> list[Any]:
    manifest = load_manifest(dataset_metadata_path())
    return manifest["documents"]


def find_dataset_document(document_id: str) -> Any:
    try:
        return find_document(
            merge_documents(
                load_dataset_documents(),
                load_uploads_manifest(storage_root()),
            ),
            document_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} was not found.",
        ) from exc


def dataclass_to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
