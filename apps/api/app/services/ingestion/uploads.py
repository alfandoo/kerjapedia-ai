from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.services.ingestion.schemas import DocumentMetadata

SOURCE_FILE_NAME = "source.pdf"
MANIFEST_FILE_NAME = "manifest.json"

TOPIC_SLUG_MAP: dict[str, list[str]] = {
    "pkwt": ["pkwt", "phk"],
    "pengupahan": ["pengupahan", "thr"],
    "bpjs": ["bpjs", "jaminan_sosial_ketenagakerjaan"],
    "k3": ["k3"],
    "hubungan_industrial": ["hubungan_industrial"],
    "waktu_kerja": ["waktu_kerja"],
}

_REGULATION_TYPE_PATTERN = re.compile(
    r"^\s*(PERPRES|PERMENAKER|PERMEN|PP|UU|UNDANG\s*[- ]?UNDANG)\b",
    re.IGNORECASE,
)
_NUMBER_YEAR_PATTERN = re.compile(r"(\d+)\s*(?:TAHUN\s+)?(\d{4})?\b", re.IGNORECASE)


def uploads_dir(storage_root: Path) -> Path:
    return storage_root / "uploads"


def uploads_manifest_path(storage_root: Path) -> Path:
    return uploads_dir(storage_root) / MANIFEST_FILE_NAME


def load_uploads_manifest(storage_root: Path) -> list[DocumentMetadata]:
    path = uploads_manifest_path(storage_root)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [DocumentMetadata.from_dict(item) for item in data["documents"]]


def _infer_regulation_fields(stem: str) -> tuple[str, int, int]:
    match = _REGULATION_TYPE_PATTERN.match(stem)
    if match:
        raw = match.group(1).replace(" ", "")
        regulation_type = {
            "UNDANG-UNDANG": "UU",
            "PERMEN": "Permenaker",
            "PP": "PP",
            "PERPRES": "Perpres",
        }.get(raw, raw.upper())
    else:
        regulation_type = "Peraturan"

    number_match = _NUMBER_YEAR_PATTERN.search(stem)
    number = int(number_match.group(1)) if number_match else 0
    year = int(number_match.group(2)) if number_match and number_match.group(2) else 0
    return regulation_type, number, year


def build_upload_document(
    document_id: str,
    file_name: str,
    topic: str,
    sha256: str,
    size_bytes: int,
    source_url: str,
    local_file: str,
) -> DocumentMetadata:
    stem = Path(file_name).stem
    regulation_type, number, year = _infer_regulation_fields(stem)
    code_match = _REGULATION_TYPE_PATTERN.match(stem)
    if code_match:
        title = code_match.group(1).upper() + " " + stem[code_match.end() :].strip().title()
    else:
        title = re.sub(r"[-_]+", " ", stem).strip().title()
    topics = TOPIC_SLUG_MAP.get(topic, [topic])
    return DocumentMetadata(
        document_id=document_id,
        title=title,
        short_title=stem[:120],
        regulation_type=regulation_type,
        number=number,
        year=year,
        issuer="",
        topics=topics,
        legal_status="needs_verification",
        source_name="Upload Admin",
        source_url=source_url,
        local_file=local_file,
        file_name=file_name,
        size_bytes=size_bytes,
        sha256=sha256,
        verification_status="pending_detail_url",
        source_verification_status="pending",
        legal_review_status="pending",
    )


def register_upload(
    storage_root: Path,
    *,
    document_id: str,
    file_name: str,
    topic: str,
    content: bytes,
    source_url: str,
) -> DocumentMetadata:
    directory = uploads_dir(storage_root) / document_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SOURCE_FILE_NAME).write_bytes(content)

    project_root = storage_root.parents[2]
    relative_local_file = (
        (storage_root / "uploads" / document_id / SOURCE_FILE_NAME)
        .relative_to(project_root)
        .as_posix()
    )
    document = build_upload_document(
        document_id=document_id,
        file_name=file_name,
        topic=topic,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        source_url=source_url,
        local_file=relative_local_file,
    )

    manifest_path = uploads_manifest_path(storage_root)
    documents = load_uploads_manifest(storage_root)
    documents = [item for item in documents if item.document_id != document_id]
    documents.append(document)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"documents": [doc.__dict__ for doc in documents]}, indent=2),
        encoding="utf-8",
    )
    return document


def merge_documents(
    dataset: list[DocumentMetadata],
    uploads: list[DocumentMetadata],
) -> list[DocumentMetadata]:
    by_id = {document.document_id: document for document in dataset}
    for document in uploads:
        by_id[document.document_id] = document
    return list(by_id.values())
