from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

MANIFEST_EDITABLE_FIELDS = {
    "title",
    "short_title",
    "regulation_type",
    "number",
    "year",
    "issuer",
    "topics",
    "legal_status",
    "source_url",
    "verification_status",
}


def update_manifest_metadata(
    manifest_path: Path, document_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = data["documents"]
    target = next(
        (document for document in documents if document.get("document_id") == document_id),
        None,
    )
    if target is None:
        raise ValueError(f"Document not found in manifest: {document_id}")

    applied: dict[str, Any] = {}
    for key, value in changes.items():
        if value is None or key not in MANIFEST_EDITABLE_FIELDS:
            continue
        target[key] = value
        applied[key] = value

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(
        prefix=f".{manifest_path.name}.", suffix=".tmp", dir=manifest_path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        manifest_path.unlink(missing_ok=True)
        Path(temp_path).replace(manifest_path)
    except BaseException:
        Path(temp_path).unlink(missing_ok=True)
        raise
    return applied


def manifest_contains(path: Path, document_id: str) -> bool:
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    return any(item.get("document_id") == document_id for item in data["documents"])
