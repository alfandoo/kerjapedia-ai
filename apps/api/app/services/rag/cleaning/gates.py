"""Tiered quality gates for the cleaning stage.

The legacy report compared segments to chunks — two views blind at the
same point. These gates additionally compare the source (article
continuity: gaps like 1,4,6… expose articles the parser never saw) and
verify the final state after dedup actions ran.
"""

from __future__ import annotations

import re

from app.services.rag.cleaning.duplicate import duplicate_groups
from app.services.rag.cleaning.schemas import CleaningReport, Gate

_ARTICLE_NUMBER_RE = re.compile(r"pasal\s+(\d+)", re.IGNORECASE)


def article_numbers(articles: set[str]) -> set[int]:
    """Extract article numbers from labels like "Pasal 12"."""
    numbers = set()
    for article in articles:
        match = _ARTICLE_NUMBER_RE.search(article or "")
        if match:
            numbers.add(int(match.group(1)))
    return numbers


def missing_article_numbers(detected: set[str]) -> list[int]:
    """Gaps in 1..max: articles the parser never produced."""
    numbers = article_numbers(detected)
    if not numbers:
        return []
    full = set(range(1, max(numbers) + 1))
    return sorted(full - numbers)


def evaluate_cleaning(
    *,
    detected_articles: set[str],
    chunk_articles: set[str],
    final_texts: list[str],
    unresolved_pages: list[int],
    heading_only_ids: list[str],
    margin_noise_ids: list[str],
    token_counts: list[int],
    max_tokens: int,
    sequential_numbering: bool = True,
) -> CleaningReport:
    """Run every gate; blocks fail the build, warns only advise."""
    missing = (
        missing_article_numbers(detected_articles) if sequential_numbering else []
    )
    unchunked = sorted(set(detected_articles) - set(chunk_articles))
    duplicates = duplicate_groups(final_texts)
    overlong = [
        index for index, count in enumerate(token_counts) if not 0 < count <= max_tokens
    ]
    gates = (
        Gate(
            gate_id="articles_detected",
            severity="block",
            passed=bool(detected_articles),
            detail=(
                f"{len(detected_articles)} articles detected"
                if detected_articles
                else "no articles detected: unstructured document needs review"
            ),
        ),
        Gate(
            gate_id="article_continuity",
            severity="block",
            passed=not missing,
            detail=f"missing articles: {missing}" if missing else "article numbers are contiguous",
        ),
        Gate(
            gate_id="detected_articles_chunked",
            severity="block",
            passed=not unchunked,
            detail=f"never chunked: {unchunked}" if unchunked else "every detected article chunked",
        ),
        Gate(
            gate_id="no_duplicate_texts",
            severity="block",
            passed=not duplicates,
            detail=f"duplicate groups: {len(duplicates)}" if duplicates else "no duplicates",
        ),
        Gate(
            gate_id="max_chunk_tokens",
            severity="block",
            passed=not overlong,
            detail=f"overlong indices: {overlong}" if overlong else "tokens within limit",
        ),
        Gate(
            gate_id="unresolved_pages",
            severity="warn",
            passed=not unresolved_pages,
            detail=f"unresolved: {unresolved_pages}" if unresolved_pages else "all resolved",
        ),
        Gate(
            gate_id="heading_only_chunks",
            severity="warn",
            passed=not heading_only_ids,
            detail=f"count: {len(heading_only_ids)}" if heading_only_ids else "none",
        ),
        Gate(
            gate_id="margin_noise_in_chunks",
            severity="warn",
            passed=not margin_noise_ids,
            detail=f"count: {len(margin_noise_ids)}" if margin_noise_ids else "none",
        ),
    )
    blocked = [
        gate.gate_id for gate in gates if gate.severity == "block" and not gate.passed
    ]
    warnings = tuple(
        f"{gate.gate_id}: {gate.detail}"
        for gate in gates
        if gate.severity == "warn" and not gate.passed
    )
    return CleaningReport(
        status="passed" if not blocked else "review_required",
        gates=gates,
        warnings=warnings,
        stats={
            "detected_articles": len(detected_articles),
            "missing_articles": missing,
            "duplicate_groups": len(duplicates),
        },
    )


__all__ = ["article_numbers", "evaluate_cleaning", "missing_article_numbers"]
