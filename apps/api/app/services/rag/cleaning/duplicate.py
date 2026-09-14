"""Duplicate detection with action, not just reporting.

Identical retrieval texts would embed to identical vectors and split
citation weight. Duplicates are removed (first occurrence wins) and the
removal is counted in the report.
"""

from __future__ import annotations

import hashlib


def _canonical(text: str) -> str:
    return " ".join(text.casefold().split())


def duplicate_groups(texts: list[str]) -> list[list[int]]:
    """Indices sharing identical canonical text, groups of 2+."""
    by_hash: dict[str, list[int]] = {}
    for index, text in enumerate(texts):
        digest = hashlib.sha256(_canonical(text).encode("utf-8")).hexdigest()
        by_hash.setdefault(digest, []).append(index)
    return [sorted(indices) for indices in by_hash.values() if len(indices) > 1]


def deduplicate_indices(texts: list[str]) -> tuple[list[int], list[int]]:
    """Split indices into (kept, removed); first occurrence always wins."""
    groups = {index: group for group in duplicate_groups(texts) for index in group}
    kept = [
        index
        for index in range(len(texts))
        if index not in groups or index == min(groups[index])
    ]
    removed = [index for index in range(len(texts)) if index not in kept]
    return kept, removed
