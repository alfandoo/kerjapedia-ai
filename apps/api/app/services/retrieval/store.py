from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.retrieval.schemas import RetrievalDocument


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _chunk_paths(storage_root: Path) -> list[Path]:
    return [
        *storage_root.glob("documents/*/v*/builds/*/processed/chunks.json"),
        *storage_root.glob("documents/*/v*/processed/chunks.json"),
    ]


def _path_context(chunks_path: Path) -> tuple[str, int, str | None]:
    processed = chunks_path.parent
    owner = processed.parent
    if owner.parent.name == "builds":
        build_id = owner.name
        version_dir = owner.parent.parent
        document_dir = version_dir.parent
    else:
        build_id = None
        version_dir = owner
        document_dir = version_dir.parent
    try:
        version = int(version_dir.name.removeprefix("v"))
    except ValueError as exc:
        raise ValueError(f"Invalid artifact version path: {chunks_path}") from exc
    return document_dir.name, version, build_id


def count_chunks_per_document(storage_root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    latest: dict[tuple[str, int], Path] = {}
    for path in _chunk_paths(storage_root):
        try:
            document_id, version, _ = _path_context(path)
        except ValueError:
            continue
        key = (document_id, version)
        current = latest.get(key)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            latest[key] = path
    for (document_id, _), path in latest.items():
        chunks = load_json(path)
        counts[document_id] = counts.get(document_id, 0) + len(chunks)
    return counts


def load_artifact_documents(
    storage_root: Path,
    eligible_versions: dict[str, int] | None = None,
    eligible_builds: dict[str, str] | None = None,
) -> list[RetrievalDocument]:
    paths = _chunk_paths(storage_root)
    selected: dict[tuple[str, int], Path] = {}
    for path in paths:
        try:
            document_id, document_version, build_id = _path_context(path)
        except ValueError:
            continue
        if eligible_versions is not None and eligible_versions.get(document_id) != document_version:
            continue
        if eligible_builds is not None:
            version_id = f"{document_id}-v{document_version}"
            if eligible_builds.get(version_id) != build_id:
                continue
        key = (document_id, document_version)
        current = selected.get(key)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            selected[key] = path

    if eligible_versions is None:
        latest_by_document: dict[str, tuple[int, Path]] = {}
        for (document_id, version), path in selected.items():
            current = latest_by_document.get(document_id)
            if current is None or path.stat().st_mtime > current[1].stat().st_mtime:
                latest_by_document[document_id] = (version, path)
        selected = {
            (document_id, version): path
            for document_id, (version, path) in latest_by_document.items()
        }

    documents: list[RetrievalDocument] = []
    for (_document_id, document_version), chunks_path in selected.items():
        _, _, build_id = _path_context(chunks_path)
        embeddings_path = chunks_path.with_name("embeddings.json")
        metadata_path = chunks_path.parents[1] / "metadata" / "document.json"
        chunks = load_json(chunks_path)
        embeddings = {}
        if embeddings_path.exists():
            embeddings = {item["chunk_id"]: item for item in load_json(embeddings_path)}
        metadata = load_json(metadata_path) if metadata_path.exists() else {}

        for chunk in chunks:
            embedded = embeddings.get(chunk["chunk_id"], {})
            documents.append(
                RetrievalDocument(
                    chunk_id=chunk["chunk_id"],
                    document_id=chunk["document_id"],
                    text=chunk["text"],
                    retrieval_text=chunk.get("retrieval_text") or chunk["text"],
                    build_id=build_id or chunk.get("build_id"),
                    chapter=chunk.get("chapter"),
                    section=chunk.get("section"),
                    article=chunk.get("article"),
                    paragraph=chunk.get("paragraph"),
                    page_start=int(chunk["page_start"]),
                    page_end=int(chunk["page_end"]),
                    token_count=int(chunk["token_count"]),
                    topics=list(chunk.get("topics", [])),
                    legal_status=chunk.get("legal_status", "needs_verification"),
                    source_url=chunk.get("source_url", ""),
                    embedding_model=embedded.get("embedding_model"),
                    embedding=embedded.get("embedding"),
                    metadata=metadata,
                    document_version=document_version,
                    publication_status=metadata.get("publication_status", "published"),
                    verification_status=metadata.get(
                        "legal_review_status",
                        metadata.get("verification_status", "verified"),
                    ),
                    is_current=True,
                    parent_text=chunk.get("parent_text"),
                    char_start=int(chunk.get("char_start", 0)),
                    char_end=int(chunk.get("char_end", 0)),
                )
            )
    return documents


@lru_cache(maxsize=8)
def load_artifact_documents_snapshot(
    storage_root: Path,
    eligible_versions: tuple[tuple[str, int], ...] | None = None,
    eligible_builds: tuple[tuple[str, str], ...] | None = None,
) -> tuple[RetrievalDocument, ...]:
    version_policy = dict(eligible_versions) if eligible_versions is not None else None
    build_policy = dict(eligible_builds) if eligible_builds is not None else None
    return tuple(load_artifact_documents(storage_root, version_policy, build_policy))


def clear_artifact_snapshot_cache() -> None:
    load_artifact_documents_snapshot.cache_clear()
