"""Output validation: segments must be sane before chunking.

Catches phantom labels, stunted segments, and broken ayat sequences —
the anomalies a single-pass parser cannot prevent by itself.
"""

from __future__ import annotations

import re

from app.services.rag.structuring.schemas import LegalSegment, SegmentIssue

_ARTICLE_LABEL_RE = re.compile(r"^Pasal \d+[A-Z]?$")
_AYAT_RE = re.compile(r"^Ayat \((\d+)\)")
_MIN_SUBSTANTIVE_CHARS = 20


def validate_segments(segments: list[LegalSegment]) -> list[SegmentIssue]:
    """Report structural anomalies; an empty list means a clean parse."""
    issues: list[SegmentIssue] = []
    issues.extend(_check_article_labels(segments))
    issues.extend(_check_minimum_length(segments))
    issues.extend(_check_ayat_sequences(segments))
    return issues


def _check_article_labels(segments: list[LegalSegment]) -> list[SegmentIssue]:
    issues = []
    for segment in segments:
        if segment.article is not None and not _ARTICLE_LABEL_RE.match(segment.article):
            issues.append(
                SegmentIssue(
                    segment_id=segment.segment_id,
                    code="bad_article_label",
                    message=f"Article label is not a clean number: {segment.article!r}",
                )
            )
    return issues


def _check_minimum_length(segments: list[LegalSegment]) -> list[SegmentIssue]:
    issues = []
    for segment in segments:
        if segment.kind != "substantive":
            continue
        if len("".join(segment.text.split())) < _MIN_SUBSTANTIVE_CHARS:
            issues.append(
                SegmentIssue(
                    segment_id=segment.segment_id,
                    code="too_short",
                    message="Substantive segment holds almost no text.",
                )
            )
    return issues


def _check_ayat_sequences(segments: list[LegalSegment]) -> list[SegmentIssue]:
    issues = []
    by_article: dict[str, list[tuple[str, int]]] = {}
    for segment in segments:
        if not segment.article or not segment.paragraph:
            continue
        match = _AYAT_RE.match(segment.paragraph)
        if match:
            by_article.setdefault(segment.article, []).append(
                (segment.segment_id, int(match.group(1)))
            )
    for article, entries in by_article.items():
        numbers = [number for _, number in entries]
        if len(set(numbers)) != len(numbers):
            issues.append(
                SegmentIssue(
                    segment_id=entries[0][0],
                    code="ayat_duplicate",
                    message=f"{article} repeats an ayat number: {numbers}",
                )
            )
        expected = list(range(1, max(numbers) + 1)) if numbers else []
        if numbers != expected:
            issues.append(
                SegmentIssue(
                    segment_id=entries[0][0],
                    code="ayat_gap",
                    message=f"{article} ayat out of sequence: {numbers}",
                )
            )
    return issues
