"""Release gate and human sampling: decide with reasons, review by risk.

- The gate aggregates probe outcomes plus golden metrics into a
  go / no-go / needs-review decision. LLM judges never block a build;
  policy reserves them for pre-major-release review.
- Human review scales through stratified sampling: every topic gets
  eyes, high-risk items first.
"""

from __future__ import annotations

from collections import defaultdict

from app.services.rag.validation.schemas import (
    GoldenReport,
    ProbeResult,
    ReleaseDecision,
    ReleaseThresholds,
)


def decide_release(
    probe_results: list[ProbeResult],
    golden: GoldenReport,
    thresholds: ReleaseThresholds | None = None,
) -> ReleaseDecision:
    """Combine probes and golden metrics into a release verdict."""
    bars = thresholds or ReleaseThresholds()
    reasons: list[str] = []
    if not probe_results and golden.evaluated == 0:
        return ReleaseDecision(
            release="needs_review",
            reasons=("no validation evidence at all",),
            metrics={
                "recall_at_k": golden.recall_at_k,
                "mrr": golden.mrr,
                "refusal_accuracy": golden.refusal_accuracy,
                "failed_probes": 0,
            },
        )
    failed_blocks = [
        result.probe_id for result in probe_results if not result.passed
    ]
    if len(failed_blocks) > bars.max_failed_block_probes:
        reasons.append(
            f"{len(failed_blocks)} blocking probes failed: {failed_blocks[:5]}"
        )
    metrics = {
        "recall_at_k": golden.recall_at_k,
        "mrr": golden.mrr,
        "refusal_accuracy": golden.refusal_accuracy,
        "failed_probes": len(failed_blocks),
    }
    if golden.evaluated and golden.recall_at_k < bars.min_recall_at_k:
        reasons.append(
            f"recall_at_k {golden.recall_at_k} below {bars.min_recall_at_k}"
        )
    if golden.evaluated and golden.mrr < bars.min_mrr:
        reasons.append(f"mrr {golden.mrr} below {bars.min_mrr}")
    if golden.refusal_accuracy < bars.min_refusal_accuracy:
        reasons.append(
            f"refusal_accuracy {golden.refusal_accuracy} below {bars.min_refusal_accuracy}"
        )
    if reasons:
        return ReleaseDecision(release="no_go", reasons=tuple(reasons), metrics=metrics)
    return ReleaseDecision(release="go", reasons=(), metrics=metrics)


_RISK_ORDER = {"high": 0, "medium": 1, "low": 2}


def stratified_sample(
    items: list, per_topic: int = 2, key_topic=None, key_risk=None, key_id=None
) -> list:
    """Pick up to ``per_topic`` items per topic, highest risk first.

    Key functions default to ``topic`` / ``risk`` / ``question_id``-style
    attributes so golden items and probes share one sampler.
    """
    topic_of = key_topic or (lambda item: item.topic)
    risk_of = key_risk or (lambda item: item.risk)
    id_of = key_id or (lambda item: getattr(item, "question_id", getattr(item, "probe_id", "")))
    buckets: dict[str, list] = defaultdict(list)
    for item in items:
        buckets[topic_of(item)].append(item)
    sampled = []
    for topic in sorted(buckets):
        ranked = sorted(
            buckets[topic],
            key=lambda item: (_RISK_ORDER.get(risk_of(item), 9), id_of(item)),
        )
        sampled.extend(ranked[: max(0, per_topic)])
    return sampled
