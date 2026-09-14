"""Consistency contract: manifest fingerprints must match the live index space.

Used by the retrieval store before any search, and by release
governance before any index transition.
"""

from app.services.rag.retrieval.consistency import (
    IndexSpaceMismatch,
    check_release_against_provider,
    verify_provider_space_at_index,
)

__all__ = [
    "IndexSpaceMismatch",
    "check_release_against_provider",
    "verify_provider_space_at_index",
]
