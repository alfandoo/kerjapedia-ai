"""Cleaning stage: tiered gates, dedup with action, auditable reports."""

from app.services.rag.cleaning.duplicate import deduplicate_indices, duplicate_groups
from app.services.rag.cleaning.gates import (
    article_numbers,
    evaluate_cleaning,
    missing_article_numbers,
)
from app.services.rag.cleaning.schemas import CleaningReport, Gate

__all__ = [
    "CleaningReport",
    "Gate",
    "article_numbers",
    "deduplicate_indices",
    "duplicate_groups",
    "evaluate_cleaning",
    "missing_article_numbers",
]
