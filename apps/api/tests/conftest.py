from collections.abc import Iterator

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def use_offline_test_providers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep tests deterministic when the developer .env selects production providers."""
    monkeypatch.setattr(settings, "vector_store", "artifact")
    monkeypatch.setattr(settings, "embedding_provider", "hash")
    monkeypatch.setattr(settings, "llm_provider", "local")
    yield
