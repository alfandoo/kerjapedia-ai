from __future__ import annotations

import json
from pathlib import Path

from app.services.ingestion.schemas import DocumentMetadata


def load_manifest(path: Path) -> dict[str, list[DocumentMetadata]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    documents = [DocumentMetadata.from_dict(item) for item in data["documents"]]
    return {"documents": documents}


def find_document(documents: list[DocumentMetadata], document_id: str) -> DocumentMetadata:
    for document in documents:
        if document.document_id == document_id:
            return document
    raise ValueError(f"Document not found in metadata manifest: {document_id}")


def duplicate_ids_by_checksum(
    documents: list[DocumentMetadata],
    sha256: str,
    current_document_id: str,
) -> list[str]:
    return [
        document.document_id
        for document in documents
        if document.sha256 == sha256 and document.document_id != current_document_id
    ]
