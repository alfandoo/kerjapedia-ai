from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class QualityStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


@dataclass(frozen=True)
class IngestionEvaluationThresholds:
    """Initial, conservative thresholds for Indonesian legal PDFs.

    Hard integrity properties use zero tolerance. Statistical thresholds are
    intentionally advisory until a larger golden corpus provides calibration.
    Callers may inject a different immutable configuration per build.
    """

    minimum_parsing_success_rate: float = 0.98
    empty_page_warning_rate: float = 0.05
    empty_page_fail_rate: float = 0.20
    low_text_character_count: int = 40
    low_text_density_warning_rate: float = 0.20
    high_text_character_count: int = 20_000
    high_text_density_fail_rate: float = 0.10
    corrupted_character_warning_rate: float = 0.001
    corrupted_character_fail_rate: float = 0.005
    minimum_useful_chunk_tokens: int = 80
    maximum_chunk_tokens: int = 550
    too_small_chunk_warning_rate: float = 0.25
    too_small_chunk_fail_rate: float = 0.60
    duplicate_chunk_warning_rate: float = 0.0
    duplicate_chunk_fail_rate: float = 0.02

    def __post_init__(self) -> None:
        rates = (
            self.minimum_parsing_success_rate,
            self.empty_page_warning_rate,
            self.empty_page_fail_rate,
            self.low_text_density_warning_rate,
            self.high_text_density_fail_rate,
            self.corrupted_character_warning_rate,
            self.corrupted_character_fail_rate,
            self.too_small_chunk_warning_rate,
            self.too_small_chunk_fail_rate,
            self.duplicate_chunk_warning_rate,
            self.duplicate_chunk_fail_rate,
        )
        if any(rate < 0 or rate > 1 for rate in rates):
            raise ValueError("ingestion evaluation rates must be between zero and one")
        if self.empty_page_warning_rate > self.empty_page_fail_rate:
            raise ValueError("empty-page warning threshold cannot exceed fail threshold")
        if self.corrupted_character_warning_rate > self.corrupted_character_fail_rate:
            raise ValueError("corruption warning threshold cannot exceed fail threshold")
        if self.too_small_chunk_warning_rate > self.too_small_chunk_fail_rate:
            raise ValueError("small-chunk warning threshold cannot exceed fail threshold")
        if self.duplicate_chunk_warning_rate > self.duplicate_chunk_fail_rate:
            raise ValueError("duplicate warning threshold cannot exceed fail threshold")
        if self.low_text_character_count < 1:
            raise ValueError("low_text_character_count must be positive")
        if self.high_text_character_count <= self.low_text_character_count:
            raise ValueError("high text threshold must exceed low text threshold")
        if not 1 <= self.minimum_useful_chunk_tokens <= self.maximum_chunk_tokens:
            raise ValueError("chunk token thresholds are invalid")

    def rationale(self) -> dict[str, str]:
        return {
            "parsing_success": (
                "Every PDF page is enumerated by the parser. Anything below 100% is "
                "reviewable; below 98% initially fails because omitted legal pages can "
                "change the meaning of a regulation."
            ),
            "empty_pages": (
                "Covers and separator pages can be empty, so up to 5% is tolerated. "
                "More than 20% strongly indicates a scanned or failed extraction."
            ),
            "text_density": (
                "The 40-character low bound reuses the active PDF quality detector. "
                "The 20,000-character high bound flags likely duplicated layout text; "
                "it is advisory unless over 10% of pages are affected."
            ),
            "corrupted_characters": (
                "The replacement/control-character limits reuse the active extractor's "
                "0.5% corruption boundary, with a lower early-warning boundary."
            ),
            "chunk_size": (
                "The 80-token useful minimum matches existing quality reporting and is "
                "advisory because valid legal provisions can be short. The 550-token "
                "maximum is the configured BGE-M3 passage ceiling and is blocking."
            ),
            "duplicates": (
                "Any exact duplicate is reported. More than 2% initially fails because "
                "duplicate vectors bias ranking and storage, pending corpus calibration."
            ),
            "provenance": (
                "Identity, page provenance, embedding parity, and index reconciliation "
                "are integrity invariants and therefore have zero tolerance."
            ),
        }


@dataclass(frozen=True)
class EvaluationFinding:
    code: str
    status: QualityStatus
    category: str
    message: str
    metric: str | None = None
    value: int | float | str | None = None
    threshold: int | float | str | None = None
    affected_items: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmbeddingEvaluationInput:
    attempted_ids: tuple[str, ...] = ()
    succeeded_ids: tuple[str, ...] = ()
    failed_ids: tuple[str, ...] = ()
    dimension_mismatch_ids: tuple[str, ...] = ()
    model: str | None = None
    revision: str | None = None
    expected_dimension: int | None = None
    error: str | None = None
    evaluated: bool = False


@dataclass(frozen=True)
class IndexingEvaluationInput:
    expected_ids: tuple[str, ...] = ()
    indexed_ids: tuple[str, ...] = ()
    evaluated: bool = False
    namespace: str | None = None
    release_id: str | None = None


@dataclass(frozen=True)
class DocumentIngestionEvaluation:
    document_id: str
    document_version: int | None
    build_id: str | None
    ingestion_version: str
    status: QualityStatus
    generated_at: str
    thresholds: dict[str, Any]
    threshold_rationale: dict[str, str]
    document: dict[str, Any]
    pages: dict[str, Any]
    structure: dict[str, Any]
    chunks: dict[str, Any]
    metadata: dict[str, Any]
    embedding: dict[str, Any]
    indexing: dict[str, Any]
    statistics: dict[str, int | float]
    findings: tuple[EvaluationFinding, ...] = ()
    schema_version: str = "ingestion-evaluation-v1"
    scope: str = "full"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CorpusIngestionEvaluation:
    status: QualityStatus
    generated_at: str
    document_count: int
    status_counts: dict[str, int]
    totals: dict[str, int | float | str | None]
    documents: tuple[dict[str, Any], ...]
    failure_reasons: dict[str, int]
    schema_version: str = "ingestion-corpus-evaluation-v1"
    scope: str = "full"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()
