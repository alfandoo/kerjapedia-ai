"""Deterministic golden evaluation: recall, MRR, refusal accuracy.

No LLM judge: the golden set carries retrieval expectations, so every
build can run the full suite in seconds. Expensive judges stay reserved
for pre-major-release review by explicit policy, not by accident.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable

from app.services.rag.validation.schemas import GoldenItem, GoldenReport

# retrieve(question, top_k) -> (ranked chunk IDs, refused?).
RetrieveFn = Callable[[str, int], tuple[list[str], bool]]


def run_golden(
    items: list[GoldenItem],
    retrieve: RetrieveFn,
    top_k: int = 5,
) -> GoldenReport:
    """Score the golden set; failures name the question IDs."""
    recalls: list[float] = []
    reciprocals: list[float] = []
    refusals: list[bool] = []
    failures: list[str] = []
    by_topic: dict[str, dict[str, float]] = defaultdict(
        lambda: {"recall": 0.0, "count": 0}
    )
    for item in items:
        ranked, refused = retrieve(item.question, top_k)
        if item.must_refuse:
            correct = refused
            refusals.append(correct)
            if not correct:
                failures.append(item.question_id)
            continue
        expected_docs = set(item.expected_document_ids)
        if not expected_docs:
            continue
        hits = [
            rank
            for rank, chunk_id in enumerate(ranked, start=1)
            if _doc_of(chunk_id) in expected_docs
        ]
        found_docs = {_doc_of(ranked[rank - 1]) for rank in hits}
        recall = len(found_docs & expected_docs) / len(expected_docs)
        recalls.append(recall)
        reciprocals.append(1.0 / hits[0] if hits else 0.0)
        by_topic[item.topic]["recall"] += recall
        by_topic[item.topic]["count"] += 1
        if recall < 1.0:
            failures.append(item.question_id)
    topic_summary = {
        topic: round(values["recall"] / values["count"], 4)
        for topic, values in by_topic.items()
        if values["count"]
    }
    return GoldenReport(
        recall_at_k=round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
        mrr=round(sum(reciprocals) / len(reciprocals), 4) if reciprocals else 0.0,
        refusal_accuracy=round(sum(refusals) / len(refusals), 4) if refusals else 1.0,
        evaluated=len(items),
        failures=tuple(failures),
        by_topic=topic_summary,
    )


_NEW_ID_RE = re.compile(r"^(.+)-v\d+-[0-9a-f]{16}$")


def _doc_of(chunk_id: str) -> str:
    """Chunk ID back to document ID, for legacy and new ID schemes."""
    if "-chunk-" in chunk_id:
        return chunk_id.split("-chunk-")[0].rsplit("-v", 1)[0]
    match = _NEW_ID_RE.match(chunk_id)
    if match:
        return match.group(1)
    return chunk_id
