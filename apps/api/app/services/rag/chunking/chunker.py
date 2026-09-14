"""Structure-aware chunking: ayat stay whole, splits are marked.

Each segment (usually one ayat) becomes chunks that fit the token
budget. Short same-article segments coalesce; oversized ones split by
sentence with part markers and sentence overlap. Chunk IDs hash content
plus structure, so identical rebuilds of a version are identical.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

from app.services.rag.chunking.schemas import Chunk, ChunkingConfig
from app.services.rag.chunking.splitter import (
    estimate_tokens,
    split_paragraphs,
    split_sentences,
)


class SegmentLike(Protocol):
    """Anything shaped like a legal segment (old or new records)."""

    document_id: str
    chapter: str | None
    section: str | None
    article: str | None
    paragraph: str | None
    page_start: int
    page_end: int
    text: str


def build_chunks(
    segments: list[SegmentLike],
    *,
    document_id: str,
    short_title: str,
    version: int,
    config: ChunkingConfig | None = None,
) -> list[Chunk]:
    """Chunk segments honoring budgets; ayat are never silently torn."""
    settings = config or ChunkingConfig()
    units = _coalesce([s for s in segments if s.text.strip()], settings)
    chunks: list[Chunk] = []
    for unit_segments in units:
        chunks.extend(
            _chunk_unit(
                unit_segments,
                document_id=document_id,
                short_title=short_title,
                version=version,
                settings=settings,
            )
        )
    return chunks


def _coalesce(
    segments: list[SegmentLike], settings: ChunkingConfig
) -> list[list[SegmentLike]]:
    """Merge short same-article segments; never merge across articles."""
    units: list[list[SegmentLike]] = []
    current: list[SegmentLike] = []
    current_tokens = 0
    for segment in segments:
        tokens = estimate_tokens(segment.text)
        same_article = (
            current
            and current[-1].article is not None
            and current[-1].article == segment.article
        )
        if (
            same_article
            and current_tokens < settings.min_merge_tokens
            and current_tokens + tokens <= settings.target_tokens
        ):
            current.append(segment)
            current_tokens += tokens
        else:
            if current:
                units.append(current)
            current = [segment]
            current_tokens = tokens
    if current:
        units.append(current)
    return units


def _chunk_unit(
    unit: list[SegmentLike],
    *,
    document_id: str,
    short_title: str,
    version: int,
    settings: ChunkingConfig,
) -> list[Chunk]:
    texts = [segment.text for segment in unit]
    if estimate_tokens("\n\n".join(texts)) <= settings.max_tokens:
        return [
            _make_chunk(
                unit,
                "\n\n".join(texts),
                part=1,
                parts=1,
                document_id=document_id,
                short_title=short_title,
                version=version,
                settings=settings,
            )
        ]
    sentences = [sentence for text in texts for sentence in _sentences_of(text)]
    parts = _pack_sentences(sentences, settings)
    chunks = []
    for index, part_sentences in enumerate(parts, start=1):
        body = " ".join(part_sentences)
        if index > 1:
            overlap = parts[index - 2][-settings.overlap_sentences :]
            body = " ".join([*overlap, body])
        chunks.append(
            _make_chunk(
                unit,
                body,
                part=index,
                parts=len(parts),
                document_id=document_id,
                short_title=short_title,
                version=version,
                settings=settings,
            )
        )
    return chunks


def _sentences_of(text: str) -> list[str]:
    sentences = []
    for paragraph in split_paragraphs(text):
        sentences.extend(split_sentences(paragraph))
    return sentences or [text]


def _pack_sentences(sentences: list[str], settings: ChunkingConfig) -> list[list[str]]:
    """Greedily pack sentences; oversized singles stand alone (hard cap
    applies to the merge target, never tearing a sentence)."""
    parts: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        tokens = estimate_tokens(sentence)
        if current and current_tokens + tokens > settings.target_tokens:
            parts.append(current)
            current = []
            current_tokens = 0
        current.append(sentence)
        current_tokens += tokens
    if current:
        parts.append(current)
    return parts or [sentences]


def _make_chunk(
    unit: list[SegmentLike],
    text: str,
    *,
    part: int,
    parts: int,
    document_id: str,
    short_title: str,
    version: int,
    settings: ChunkingConfig,
) -> Chunk:
    first, last = unit[0], unit[-1]
    header = " | ".join(
        part
        for part in [
            short_title,
            first.article,
            first.paragraph if first.paragraph == last.paragraph else None,
        ]
        if part
    )
    if parts > 1:
        note = f"(bagian {part} dari {parts})"
        header = f"{header} {note}" if header else note
    retrieval_text = f"{header}\n{text}" if header else text
    parent = "\n\n".join(segment.text for segment in unit)
    digest = hashlib.sha256(
        f"{document_id}\nv{version}\n{first.article}\n{first.paragraph}\n{text}".encode()
    ).hexdigest()[:16]
    return Chunk(
        chunk_id=f"{document_id}-v{version}-{digest}",
        document_id=document_id,
        short_title=short_title,
        chapter=first.chapter,
        section=first.section,
        article=first.article,
        paragraph=first.paragraph if first.paragraph == last.paragraph else None,
        page_start=first.page_start,
        page_end=last.page_end,
        text=text,
        retrieval_text=retrieval_text,
        parent_text=_truncate_words(parent, settings.parent_tokens),
        token_estimate=estimate_tokens(text),
        part=part,
        parts=parts,
        continued=parts > 1,
    )


def _truncate_words(text: str, max_words: int) -> str:
    """Cap parent context by words (a rough stand-in for tokens)."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])
