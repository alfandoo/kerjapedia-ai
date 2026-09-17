"""Consistency contract: manifest fingerprints must match the live index space.

Used by the retrieval store before any search, and by release
governance before any index transition.
"""

from __future__ import annotations

from app.services.rag.embedding.schemas import EmbeddingConfig, vector_space_id
from app.services.rag.indexing.schemas import ReleaseManifest


class IndexSpaceMismatch(Exception):
    """Raised when a manifest's model space does not match the provider."""


def check_release_against_provider(
    manifest: ReleaseManifest, config: EmbeddingConfig
) -> tuple[bool, str | None]:
    """Compare a release manifest's model_space against the embedding config.

    Returns (compatible, detail) where detail is None on match or a
    human-readable mismatch description on failure.
    """
    expected = vector_space_id(config)
    if manifest.model_space == expected:
        return True, None
    return False, (
        f"Manifest model_space {manifest.model_space!r} does not match "
        f"provider space {expected!r} (model={config.model_name})"
    )


def verify_provider_space_at_index(
    manifest: ReleaseManifest, config: EmbeddingConfig
) -> None:
    """Raise ``IndexSpaceMismatch`` if the manifest and config diverge."""
    compatible, detail = check_release_against_provider(manifest, config)
    if not compatible:
        raise IndexSpaceMismatch(detail)
