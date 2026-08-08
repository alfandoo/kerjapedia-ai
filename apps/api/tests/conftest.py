from collections.abc import Iterator

import pytest

from app.core.config import settings


@pytest.fixture(scope="session", autouse=True)
def ensure_test_schema() -> Iterator[None]:
    """Create missing tables (e.g. audit_logs) without touching existing rows."""
    from app.db.session import ensure_schema

    ensure_schema()
    yield


@pytest.fixture(autouse=True)
def use_offline_test_providers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep tests deterministic when the developer .env selects production providers."""
    monkeypatch.setattr(settings, "vector_store", "artifact")
    monkeypatch.setattr(settings, "embedding_provider", "hash")
    monkeypatch.setattr(settings, "llm_provider", "local")
    yield


@pytest.fixture(autouse=True)
def restore_dataset_manifest() -> Iterator[None]:
    """Restore dataset/metadata.json after tests that exercise metadata updates."""
    from app.api.utils import dataset_metadata_path

    path = dataset_metadata_path()
    original = path.read_bytes()
    yield
    path.write_bytes(original)
