"""Production architecture guardrails (audit, not exhaustive E2E)."""

import pathlib


def test_storage_does_not_fabricate_public_urls():
    src = pathlib.Path("app/services/storage.py").read_text(encoding="utf-8")
    assert "Supabase Storage" in src
    assert "create_signed_url" in src
    assert "/object/public/" not in src or "Legacy" in src or "legacy" in src.lower()


def test_upstash_indexing_does_not_fabricate_governance():
    src = pathlib.Path("app/services/ingestion/upstash_indexing.py").read_text(
        encoding="utf-8"
    )
    assert '"publication_status": "published"' not in src
    assert '"verification_status": "verified"' not in src
    assert "Neon" in src


def test_reembed_is_async_and_governed():
    src = pathlib.Path("app/api/routes_ingestion.py").read_text(encoding="utf-8")
    assert "_collect_governed_chunks" in src
    assert "yield_per" in src
    assert "BackgroundTasks" in src or "background_tasks" in src


def test_render_has_worker_and_rest_names():
    src = pathlib.Path("../../render.yaml").read_text(encoding="utf-8")
    assert "kerjapedia-worker" in src
    assert "UPSTASH_VECTOR_REST_URL" in src
    assert "Neon PostgreSQL" in src


def test_env_example_groups_ownership():
    src = pathlib.Path("../../.env.example").read_text(encoding="utf-8")
    assert "Neon PostgreSQL" in src
    assert "SUPABASE_STORAGE_BUCKET" in src
    assert "UPSTASH_VECTOR_REST_URL" in src
    assert "CELERY_ENABLED" in src
