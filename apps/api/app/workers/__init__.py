"""Async worker entrypoint — shared Celery app.

Render runs ``kerjapedia-worker`` (and optional ``kerjapedia-scheduler``)
as separate services from ``kerjapedia-api``. The FastAPI process only
validates, persists metadata, and enqueues; heavy OCR/parsing/indexing
runs here. Importing from this package re-exports the canonical Celery
app so ``celery -A app.workers.celery_app`` stays stable even if task
modules move.
"""

try:
    from app.services.ingestion.tasks import celery_app
except Exception:  # pragma: no cover - celery optional in minimal dev installs
    celery_app = None  # type: ignore[assignment]

__all__ = ["celery_app"]
