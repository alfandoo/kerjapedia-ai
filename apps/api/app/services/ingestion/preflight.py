from __future__ import annotations

import json

from app.core.config import settings
from app.services.ingestion.builds import (
    build_config_from_settings,
    validate_candidate_runtime,
)
from app.services.providers import embedding_provider_from_settings


def main() -> None:
    provider = embedding_provider_from_settings(
        settings,
        require_native_sparse=True,
    )
    config = build_config_from_settings(
        settings,
        provider,
        release_candidate=True,
    )
    validate_candidate_runtime(config)
    print(
        json.dumps(
            {
                "status": "ready",
                "pipeline_version": config.pipeline_version,
                "config_hash": config.config_hash,
                "embedding_model": config.embedding_model,
                "embedding_revision": config.embedding_revision,
                "runtime": config.runtime,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
