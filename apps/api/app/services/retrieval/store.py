from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.retrieval.schemas import RetrievalDocument


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_artifact_documents(storage_root: Path) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []

    for chunks_path in storage_root.glob("documents/*/v*/processed/chunks.json"):
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
                )
            )

    return documents
