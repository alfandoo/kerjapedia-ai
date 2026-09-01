from __future__ import annotations

import hashlib
import re
from dataclasses import replace

from app.services.ingestion.schemas import Chunk, DocumentMetadata, LegalSegment

HEADING_ONLY_RE = re.compile(
    r"^\s*(?:BAB\s+[IVXLCDM]+|Bagian\s+\S+(?:\s+\S+){0,3}|"
    r"Paragraf\s+\S+(?:\s+\S+){0,3}|Pasal\s+\d+[A-Z]?)\s*$",
    re.IGNORECASE,
)


def estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE)))


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
    max_chars: int | None = None,
    overlap_chars: int = 180,
    target_tokens: int = 350,
    max_tokens: int = 550,
    overlap_tokens: int = 60,
    min_merge_tokens: int = 180,
    parent_tokens: int = 1200,
    build_id: str | None = None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    counter = 1
    prepared = _coalesce_short_segments(
        [segment for segment in segments if not HEADING_ONLY_RE.fullmatch(segment.text.strip())],
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        min_merge_tokens=min_merge_tokens,
    )

    for segment in prepared:
        if max_chars is not None:
            parts = [
                (text, segment.text.find(text), segment.text.find(text) + len(text))
                for text in split_text(
                    segment.text,
                    max_chars=max_chars,
                    overlap_chars=min(overlap_chars, max(0, max_chars // 5)),
                )
            ]
        else:
            parts = split_legal_text_by_tokens(
                segment.text,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
            )
        parent_text = _truncate_tokens(segment.text, parent_tokens)
        for text_part, char_start, char_end in parts:
            if not text_part or HEADING_ONLY_RE.fullmatch(text_part.strip()):
                continue
            retrieval_text = build_retrieval_text(document, segment, text_part)
            short_build = build_id[-12:] if build_id else None
            chunk_id = (
                f"{document.document_id}-v{version}-b{short_build}-chunk-{counter:05d}"
                if short_build
                else f"{document.document_id}-v{version}-chunk-{counter:05d}"
            )
            checksum = hashlib.sha256(f"{chunk_id}\n{retrieval_text}".encode()).hexdigest()
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
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
                    parent_text=parent_text,
                    char_start=char_start,
                    char_end=char_end,
                    build_id=build_id,
                    retrieval_text=retrieval_text,
                    chunk_type=segment.segment_type,
                    artifact_checksum=checksum,
                )
            )
            counter += 1

    return chunks


def build_retrieval_text(
    document: DocumentMetadata,
    segment: LegalSegment,
    text: str,
) -> str:
    path = [
        document.title,
        segment.chapter,
        segment.section,
        segment.article,
        segment.paragraph,
    ]
    lines: list[str] = []
    for value in [*path, text]:
        if value and (not lines or lines[-1] != value):
            lines.append(value)
    return "\n".join(lines)


def split_legal_text_by_tokens(
    text: str,
    *,
    target_tokens: int,
    max_tokens: int,
    overlap_tokens: int,
) -> list[tuple[str, int, int]]:
    spans = list(re.finditer(r"\S+", text))
    if len(spans) <= max_tokens:
        return [(text.strip(), 0, len(text))]
    chunks: list[tuple[str, int, int]] = []
    start_token = 0
    while start_token < len(spans):
        end_token = min(start_token + target_tokens, len(spans))
        search_limit = min(start_token + max_tokens, len(spans))
        if end_token < len(spans):
            for candidate in range(end_token, search_limit):
                whitespace = text[spans[candidate - 1].end() : spans[candidate].start()]
                if "\n" in whitespace or spans[candidate - 1].group().endswith((".", ";")):
                    end_token = candidate
                    break
        start = spans[start_token].start()
        end = spans[end_token - 1].end()
        chunks.append((text[start:end].strip(), start, end))
        if end_token >= len(spans):
            break
        start_token = max(start_token + 1, end_token - overlap_tokens)
    return chunks


def _coalesce_short_segments(
    segments: list[LegalSegment],
    *,
    target_tokens: int,
    max_tokens: int,
    min_merge_tokens: int,
) -> list[LegalSegment]:
    result: list[LegalSegment] = []
    current: LegalSegment | None = None
    for segment in segments:
        if current is None:
            current = segment
            continue
        current_tokens = estimate_tokens(current.text)
        combined_tokens = current_tokens + estimate_tokens(segment.text)
        same_boundary = (
            current.article == segment.article
            and current.chapter == segment.chapter
            and current.section == segment.section
            and current.segment_type == segment.segment_type
        )
        should_merge = (
            same_boundary
            and combined_tokens <= max_tokens
            and (current_tokens < min_merge_tokens or combined_tokens <= target_tokens)
        )
        if should_merge:
            current = _merge_segments(current, segment)
        else:
            result.append(current)
            current = segment
    if current is not None:
        if (
            result
            and estimate_tokens(current.text) < min_merge_tokens
            and _same_legal_boundary(result[-1], current)
            and estimate_tokens(result[-1].text) + estimate_tokens(current.text) <= max_tokens
        ):
            result[-1] = _merge_segments(result[-1], current)
        else:
            result.append(current)
    return result


def _same_legal_boundary(left: LegalSegment, right: LegalSegment) -> bool:
    return (
        left.article == right.article
        and left.chapter == right.chapter
        and left.section == right.section
        and left.segment_type == right.segment_type
    )


def _merge_segments(left: LegalSegment, right: LegalSegment) -> LegalSegment:
    paragraph = left.paragraph if left.paragraph == right.paragraph else None
    return replace(
        left,
        paragraph=paragraph,
        page_end=max(left.page_end, right.page_end),
        text=f"{left.text}\n{right.text}".strip(),
    )


def _truncate_tokens(text: str, limit: int) -> str:
    spans = list(re.finditer(r"\S+", text))
    if len(spans) <= limit:
        return text
    return text[: spans[limit - 1].end()].rstrip()
