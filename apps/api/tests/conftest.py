import os
from collections.abc import Iterator

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/kerjapedia_test",
)

import pytest

from app.core.config import settings


@pytest.fixture(scope="session")
def verify_test_schema() -> Iterator[None]:
    """Require the isolated test database to be migrated before tests run."""
    from app.db.session import assert_schema_current

    assert_schema_current()
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
