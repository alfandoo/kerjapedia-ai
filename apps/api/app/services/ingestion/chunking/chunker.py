"""Structure-aware, token-enforced chunking for Indonesian legal documents."""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass, replace

from app.services.ingestion.chunking.models import (
    ChunkingConfig,
    ChunkingResult,
    ChunkStatistics,
)
from app.services.ingestion.chunking.tokenizer import Tokenizer, TokenSpan
from app.services.ingestion.domain import (
    Chunk,
    LegalSection,
    StructuredLegalDocument,
    content_sha256,
)


@dataclass(frozen=True)
class _TextPart:
    content: str
    overlap_tokens: int


class StructureAwareChunker:
    """Chunk Pasal first, Ayat second, and token spans only as a fallback."""

    def __init__(self, tokenizer: Tokenizer, config: ChunkingConfig | None = None) -> None:
        self.tokenizer = tokenizer
        self.config = config or ChunkingConfig()

    def chunk(self, structured: StructuredLegalDocument) -> ChunkingResult:
        self._structured = structured
        self._section_by_id = {
            section.node_id: section
            for section in structured.sections
            if section.node_id is not None
        }
        chunks: list[Chunk] = []
        for section in self._primary_sections(structured.sections):
            if section.type == "pasal":
                chunks.extend(self._chunk_pasal(section))
            else:
                chunks.extend(self._chunk_fallback_section(section))
        return ChunkingResult(
            chunks=tuple(chunks),
            statistics=calculate_chunk_statistics(chunks),
        )

    def _primary_sections(
        self,
        sections: tuple[LegalSection, ...],
    ) -> list[LegalSection]:
        selected = []
        for section in sections:
            if section.source_duplicate_of or any(
                node.source_duplicate_of for node in self._section_path(section)
            ):
                continue
            ancestors = self._section_path(section)[:-1]
            if any(node.type == "pasal" for node in ancestors):
                continue  # Already represented by the complete Pasal.
            if section.type == "pasal":
                selected.append(section)
                continue
            # Preserve opening, explanatory and attachment text as well as
            # Pasal. Parents store inclusive text: subtract only exact direct
            # child ranges to avoid indexing the same descendant twice.
            own_text = self._parent_intro_text(section)
            heading_only = "".join(own_text.split()).rstrip(":").casefold() in {
                "".join(section.identifier.split()).casefold(),
                "".join(f"{section.identifier}{section.title or ''}".split()).casefold(),
            }
            if own_text and not heading_only:
                selected.append(replace(section, text=own_text))
        return selected

    def _parent_intro_text(self, section: LegalSection) -> str:
        """Return only a parent's text before its first direct child.

        Parser nodes are inclusive. Removing every child by string replacement
        can leave suffixes from nested Pasal in a Lampiran chunk, which loses
        Pasal provenance. The parent preamble is the only independent text.
        """
        starts = [
            section.text.find(child.text)
            for child_id in section.children
            if (child := self._section_by_id.get(child_id)) and child.text
            and section.text.find(child.text) >= 0
        ]
        return section.text[: min(starts)].strip() if starts else section.text.strip()

    def _chunk_pasal(self, pasal: LegalSection) -> list[Chunk]:
        if self.tokenizer.count(pasal.text) <= self.config.max_tokens:
            return [self._make_chunk(pasal, pasal.text, "pasal", 1, 1, 0)]

        ayats = [
            self._section_by_id[child_id]
            for child_id in pasal.children
            if child_id in self._section_by_id and self._section_by_id[child_id].type == "ayat"
        ]
        if not ayats:
            return self._split_pasal_without_ayat(pasal)

        chunks: list[Chunk] = []
        intro = _pasal_intro(pasal, ayats[0])
        if intro:
            chunks.extend(
                self._chunks_from_parts(
                    pasal,
                    prefix=pasal.identifier,
                    body=intro,
                    separator="\n",
                    chunk_type="pasal_intro",
                )
            )
        for ayat in ayats:
            marker = _ayat_marker(ayat.identifier)
            body = _strip_leading_marker(ayat.text, marker)
            chunks.extend(
                self._chunks_from_parts(
                    ayat,
                    prefix=f"{pasal.identifier}\n{marker}",
                    body=body,
                    separator=" ",
                    chunk_type="ayat",
                )
            )
        return chunks

    def _split_pasal_without_ayat(self, pasal: LegalSection) -> list[Chunk]:
        body = _strip_leading_marker(pasal.text, pasal.identifier)
        return self._chunks_from_parts(
            pasal,
            prefix=pasal.identifier,
            body=body,
            separator="\n",
            chunk_type="pasal",
        )

    def _chunk_fallback_section(self, section: LegalSection) -> list[Chunk]:
        return self._chunks_from_parts(
            section,
            prefix=section.identifier,
            body=_strip_leading_marker(section.text, section.identifier),
            separator="\n",
            chunk_type=section.type,
        )

    def _chunks_from_parts(
        self,
        section: LegalSection,
        *,
        prefix: str,
        body: str,
        separator: str,
        chunk_type: str,
    ) -> list[Chunk]:
        parts = self._split_with_token_budget(prefix, body, separator)
        part_count = len(parts)
        return [
            self._make_chunk(
                section,
                part.content,
                chunk_type if part_count == 1 else f"{chunk_type}_continuation",
                part_number,
                part_count,
                part.overlap_tokens,
            )
            for part_number, part in enumerate(parts, start=1)
        ]

    def _split_with_token_budget(
        self,
        prefix: str,
        body: str,
        separator: str,
    ) -> list[_TextPart]:
        complete = _compose(prefix, body, separator)
        if self.tokenizer.count(complete) <= self.config.max_tokens:
            return [_TextPart(complete, 0)]

        prefix_tokens = self.tokenizer.count(prefix)
        if prefix_tokens >= self.config.max_tokens:
            raise ValueError(
                f"Legal prefix exceeds max_tokens={self.config.max_tokens}: {prefix!r}"
            )
        spans = self.tokenizer.spans(body)
        if not spans:
            raise ValueError("A legal section exceeded max_tokens but has no splittable body")

        max_body_tokens = max(1, self.config.max_tokens - prefix_tokens - 1)
        min_body_tokens = max(1, self.config.min_tokens - prefix_tokens)
        target_body_tokens = max(
            min_body_tokens,
            self.config.target_tokens - prefix_tokens - 1,
        )
        target_body_tokens = min(target_body_tokens, max_body_tokens)

        parts: list[_TextPart] = []
        start_token = 0
        while start_token < len(spans):
            hard_end = min(start_token + max_body_tokens, len(spans))
            preferred_end = min(start_token + target_body_tokens, hard_end)
            remaining = len(spans) - preferred_end
            if 0 < remaining < min_body_tokens:
                preferred_end = max(start_token + min_body_tokens, len(spans) - min_body_tokens)
                preferred_end = min(preferred_end, hard_end)
            end_token = _semantic_end(
                body,
                spans,
                start_token=start_token,
                preferred_end=preferred_end,
                hard_end=hard_end,
                min_body_tokens=min_body_tokens,
            )
            content = self._content_from_span(
                prefix,
                body,
                separator,
                spans,
                start_token,
                end_token,
            )
            while (
                end_token > start_token + 1
                and self.tokenizer.count(content) > self.config.max_tokens
            ):
                end_token -= 1
                content = self._content_from_span(
                    prefix,
                    body,
                    separator,
                    spans,
                    start_token,
                    end_token,
                )
            if self.tokenizer.count(content) > self.config.max_tokens:
                raise ValueError("Tokenizer could not produce a chunk within max_tokens")

            overlap = 0
            if end_token < len(spans):
                # Overlap exists only for token fallback splits and is capped
                # at 10% of the current body part to prevent context inflation.
                overlap = min(
                    self.config.overlap_tokens,
                    max(0, (end_token - start_token) // 10),
                )
            parts.append(_TextPart(content, overlap))
            if end_token >= len(spans):
                break
            start_token = max(start_token + 1, end_token - overlap)
        return parts

    @staticmethod
    def _content_from_span(
        prefix: str,
        body: str,
        separator: str,
        spans: tuple[TokenSpan, ...],
        start_token: int,
        end_token: int,
    ) -> str:
        start = spans[start_token].start
        end = spans[end_token - 1].end
        return _compose(prefix, body[start:end].strip(), separator)

    def _make_chunk(
        self,
        section: LegalSection,
        content: str,
        chunk_type: str,
        part_number: int,
        part_count: int,
        overlap_tokens: int,
    ) -> Chunk:
        token_count = self.tokenizer.count(content)
        if token_count > self.config.max_tokens:
            raise ValueError(
                f"Chunk for {section.identifier} has {token_count} tokens; "
                f"maximum is {self.config.max_tokens}"
            )
        path = self._section_path(section)
        hierarchy = _legal_hierarchy(path)
        content_hash = content_sha256(content)
        document = self._structured.document
        identity = "\n".join(
            (
                document.document_id,
                document.ingestion_version,
                document.file_hash,
                section.node_id or section.identifier,
                str(part_number),
                content_hash,
            )
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        chunk_id = f"{document.document_id}-{digest}"
        metadata = {
            "document_id": document.document_id,
            "document_title": document.title,
            "source": document.source,
            "source_url": document.source_url,
            "file_hash": document.file_hash,
            "ingestion_version": document.ingestion_version,
            "structure_schema_version": self._structured.schema_version,
            "section_node_id": section.node_id,
            "section_type": section.type,
            "section_identifier": section.identifier,
            "section_path": [node.identifier for node in path],
            "legal_hierarchy": hierarchy,
            "tokenizer": self.tokenizer.name,
            "tokenizer_revision": self.tokenizer.revision,
            "target_tokens": self.config.target_tokens,
            "max_tokens": self.config.max_tokens,
            "minimum_useful_tokens": self.config.min_tokens,
            "overlap_tokens": overlap_tokens,
            "part_number": part_number,
            "part_count": part_count,
        }
        return Chunk(
            chunk_id=chunk_id,
            document_id=document.document_id,
            content=content,
            page_start=section.page_start,
            page_end=section.page_end,
            legal_hierarchy=hierarchy,
            metadata=metadata,
            content_hash=content_hash,
            parent_chunk_id=None,
            section_path=tuple(node.identifier for node in path),
            source=document.source,
            source_url=document.source_url,
            token_count=token_count,
            chunk_type=chunk_type,
            part_number=part_number,
            part_count=part_count,
        )

    def _section_path(self, section: LegalSection) -> list[LegalSection]:
        path = [section]
        seen = {section.node_id}
        parent_id = section.parent
        while parent_id and parent_id in self._section_by_id and parent_id not in seen:
            parent = self._section_by_id[parent_id]
            seen.add(parent_id)
            if parent.type != "document":
                path.append(parent)
            parent_id = parent.parent
        path.reverse()
        return path


def chunk_legal_document(
    structured: StructuredLegalDocument,
    *,
    tokenizer: Tokenizer,
    config: ChunkingConfig | None = None,
) -> ChunkingResult:
    """Chunk a structured document with an explicitly selected tokenizer."""
    return StructureAwareChunker(
        tokenizer,
        config=config,
    ).chunk(structured)


def calculate_chunk_statistics(chunks: list[Chunk]) -> ChunkStatistics:
    counts = sorted(chunk.token_count for chunk in chunks)
    if not counts:
        return ChunkStatistics(0, 0, 0, 0.0, 0.0, 0.0, 0.0)
    return ChunkStatistics(
        number_of_chunks=len(counts),
        min_tokens=counts[0],
        max_tokens=counts[-1],
        mean_tokens=statistics.fmean(counts),
        median_tokens=statistics.median(counts),
        p95_tokens=_percentile(counts, 0.95),
        p99_tokens=_percentile(counts, 0.99),
    )


def _semantic_end(
    text: str,
    spans: tuple[TokenSpan, ...],
    *,
    start_token: int,
    preferred_end: int,
    hard_end: int,
    min_body_tokens: int,
) -> int:
    lower = min(hard_end, start_token + min_body_tokens)
    for end_token in range(preferred_end, lower - 1, -1):
        if _is_semantic_boundary(text, spans, end_token):
            return end_token
    for end_token in range(preferred_end + 1, hard_end + 1):
        if _is_semantic_boundary(text, spans, end_token):
            return end_token
    return max(start_token + 1, preferred_end)


def _is_semantic_boundary(
    text: str,
    spans: tuple[TokenSpan, ...],
    end_token: int,
) -> bool:
    if end_token <= 0 or end_token > len(spans):
        return False
    end = spans[end_token - 1].end
    stripped = text[:end].rstrip()
    if stripped.endswith((".", ";", ":", "?", "!")):
        return True
    if end_token < len(spans):
        gap = text[end : spans[end_token].start]
        return "\n" in gap
    return True


def _pasal_intro(pasal: LegalSection, first_ayat: LegalSection) -> str:
    body = _strip_leading_marker(pasal.text, pasal.identifier)
    position = body.find(first_ayat.text)
    return body[:position].strip() if position >= 0 else ""


def _ayat_marker(identifier: str) -> str:
    return identifier.removeprefix("Ayat ").strip()


def _strip_leading_marker(text: str, marker: str) -> str:
    stripped = text.strip()
    if stripped.casefold().startswith(marker.casefold()):
        return stripped[len(marker) :].lstrip(" \t\r\n:.")
    return stripped


def _compose(prefix: str, body: str, separator: str) -> str:
    if not body:
        return prefix.strip()
    return f"{prefix.strip()}{separator}{body.strip()}"


def _legal_hierarchy(path: list[LegalSection]) -> dict[str, str]:
    hierarchy: dict[str, str] = {}
    prefixes = {
        "bab": "BAB ",
        "bagian": "Bagian ",
        "paragraf": "Paragraf ",
        "pasal": "Pasal ",
        "ayat": "Ayat ",
    }
    for node in path:
        if node.amendment_scope:
            hierarchy["amendment_scope"] = node.amendment_scope
        if node.type in prefixes:
            value = node.identifier.removeprefix(prefixes[node.type]).strip()
            hierarchy[node.type] = value.strip("()")
        elif node.type in {"penjelasan", "lampiran"}:
            hierarchy["document_section"] = node.identifier
        if node.role:
            hierarchy["role"] = node.role
    return hierarchy


def _percentile(sorted_values: list[int], quantile: float) -> float:
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[lower])
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction
