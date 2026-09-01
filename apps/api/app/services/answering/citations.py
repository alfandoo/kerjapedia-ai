from __future__ import annotations

import re

from app.services.answering.schemas import Citation, RelatedDocument
from app.services.retrieval.schemas import RankedChunk

_WHITESPACE_RE = re.compile(r"\s+")


def compact_text(value: str, limit: int = 260) -> str:
    compacted = _WHITESPACE_RE.sub(" ", value).strip()
    if len(compacted) <= limit:
        return compacted
    return f"{compacted[: limit - 3].rstrip()}..."


def build_citations(ranked: list[RankedChunk]) -> list[Citation]:
    citations: list[Citation] = []
    seen_chunks: set[str] = set()

    for item in ranked:
        document = item.document
        if document.chunk_id in seen_chunks:
            continue
        seen_chunks.add(document.chunk_id)
        metadata = document.metadata
        citation_number = len(citations) + 1
        citations.append(
            Citation(
                citation_id=f"cit_{citation_number:03d}",
                chunk_id=document.chunk_id,
                document_id=document.document_id,
                document_title=metadata.get("title") or document.document_id,
                short_title=metadata.get("short_title") or document.document_id,
                legal_status=document.legal_status,
                chapter=document.chapter,
                section=document.section,
                article=document.article,
                paragraph=document.paragraph,
                page_start=document.page_start,
                page_end=document.page_end,
                quote=compact_text(document.text),
                source_url=document.source_url,
                local_file=metadata.get("local_file"),
                retrieval_score=item.final_score,
                rerank_score=item.rerank_score,
                document_version=document.document_version,
            )
        )

    return citations


def build_related_documents(ranked: list[RankedChunk]) -> list[RelatedDocument]:
    related: list[RelatedDocument] = []
    seen_documents: set[str] = set()

    for item in ranked:
        document = item.document
        if document.document_id in seen_documents:
            continue
        seen_documents.add(document.document_id)
        metadata = document.metadata
        related.append(
            RelatedDocument(
                document_id=document.document_id,
                title=metadata.get("title") or document.document_id,
                short_title=metadata.get("short_title") or document.document_id,
                legal_status=document.legal_status,
                source_url=document.source_url,
            )
        )

    return related
