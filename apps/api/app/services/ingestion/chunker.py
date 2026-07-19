from __future__ import annotations

from app.services.ingestion.schemas import Chunk, DocumentMetadata, LegalSegment


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        window = text[start:end]
        split_at = max(window.rfind("\n"), window.rfind(". "))
        if split_at > max_chars * 0.5:
            end = start + split_at + 1
            window = text[start:end]
        chunks.append(window.strip())
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    return [chunk for chunk in chunks if chunk]


def build_chunks(
    document: DocumentMetadata,
    segments: list[LegalSegment],
    version: int,
    max_chars: int = 1800,
    overlap_chars: int = 180,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    counter = 1

    for segment in segments:
        for text_part in split_text(segment.text, max_chars=max_chars, overlap_chars=overlap_chars):
            chunks.append(
                Chunk(
                    chunk_id=f"{document.document_id}-v{version}-chunk-{counter:05d}",
                    document_id=document.document_id,
                    chapter=segment.chapter,
                    section=segment.section,
                    article=segment.article,
                    paragraph=segment.paragraph,
                    page_start=segment.page_start,
                    page_end=segment.page_end,
                    text=text_part,
                    token_count=estimate_tokens(text_part),
                    topics=document.topics,
                    legal_status=document.legal_status,
                    source_url=document.source_url,
                )
            )
            counter += 1

    return chunks
