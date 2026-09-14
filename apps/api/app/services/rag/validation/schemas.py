"""Validation records: probes, golden results, and release decisions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Probe:
    """One executable check with its expectation."""

    probe_id: str
    kind: str  # retrieval_spot | article_coverage | refusal
    document_id: str = ""
    topic: str = ""
    risk: str = "low"  # low | medium | high
    query: str = ""
    expected_chunk_ids: tuple[str, ...] = ()
    expected_articles: tuple[str, ...] = ()
    must_refuse: bool = False


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of one probe: pass/fail plus the evidence."""

    probe_id: str
    passed: bool
    detail: str = ""
    latency_ms: int = 0


@dataclass(frozen=True)
class GoldenItem:
    """One golden question with retrieval expectations (no LLM needed)."""

    question_id: str
    question: str
    topic: str = ""
    risk: str = "low"
    expected_document_ids: tuple[str, ...] = ()
    expected_articles: tuple[str, ...] = ()
    must_refuse: bool = False


@dataclass(frozen=True)
class GoldenReport:
    """Deterministic retrieval metrics over the golden set."""

    recall_at_k: float = 0.0
    mrr: float = 0.0
    refusal_accuracy: float = 0.0
    evaluated: int = 0
    failures: tuple[str, ...] = ()
    by_topic: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ReleaseThresholds:
    """Go/no-go bars. Breach any block and the release waits."""

    min_recall_at_k: float = 0.7
    min_mrr: float = 0.5
    min_refusal_accuracy: float = 0.8
    max_failed_block_probes: int = 0


@dataclass(frozen=True)
class ReleaseDecision:
    """A release verdict with every reason attached."""

    release: str  # go | no_go | needs_review
    reasons: tuple[str, ...] = ()
    metrics: dict = field(default_factory=dict)
