"""Executable probes: spot retrieval and article coverage.

Probes run against any search function returning ranked chunk IDs, so
the same checks guard unit tests, builds, and the live namespace.
"""

from __future__ import annotations

from collections.abc import Callable

from app.services.rag.cleaning.gates import missing_article_numbers
from app.services.rag.validation.schemas import Probe, ProbeResult

# search_fn(question, top_k) -> ranked chunk IDs.
SearchFn = Callable[[str, int], list[str]]


def run_spot_probe(search: SearchFn, probe: Probe, top_k: int = 5) -> ProbeResult:
    """An expected chunk must rank within top-k for its probe query."""
    ranked = search(probe.query, top_k)
    hit = next(
        (chunk_id for chunk_id in probe.expected_chunk_ids if chunk_id in ranked),
        None,
    )
    if hit is None:
        return ProbeResult(
            probe_id=probe.probe_id,
            passed=False,
            detail=f"none of {list(probe.expected_chunk_ids)} in top-{top_k}",
        )
    return ProbeResult(
        probe_id=probe.probe_id,
        passed=True,
        detail=f"{hit} ranked #{ranked.index(hit) + 1}",
    )


def run_article_coverage_probe(
    probe_id: str,
    document_id: str,
    detected_articles: set[str],
    chunk_articles: set[str],
    *,
    sequential_numbering: bool = True,
) -> ProbeResult:
    """Every article the source carries must survive into chunks.

    This is the check that would have caught the lost Pasal 2, 3, 5:
    it compares the source against the parse, not the parse against
    itself. Amendment regulations (``PERUBAHAN``) number non-sequentially
    and use Roman numerals — pass ``sequential_numbering=False`` for them
    instead of manufacturing false gaps.
    """
    problems = []
    if not detected_articles:
        problems.append("no articles detected at all")
    if sequential_numbering:
        missing = missing_article_numbers(detected_articles)
        if missing:
            problems.append(f"never parsed: {missing}")
    unchunked = sorted(set(detected_articles) - set(chunk_articles))
    if unchunked:
        problems.append(f"never chunked: {unchunked}")
        problems.append(f"never parsed: {missing}")
    if unchunked:
        problems.append(f"never chunked: {unchunked}")
    if problems:
        return ProbeResult(
            probe_id=probe_id, passed=False, detail="; ".join(problems)
        )
    return ProbeResult(
        probe_id=probe_id,
        passed=True,
        detail=f"{document_id}: {len(detected_articles)} articles covered",
    )


def run_probes(
    search: SearchFn, probes: list[Probe], top_k: int = 5
) -> list[ProbeResult]:
    """Run spot probes; coverage probes need article sets, not search."""
    return [
        run_spot_probe(search, probe, top_k)
        for probe in probes
        if probe.kind == "retrieval_spot"
    ]
