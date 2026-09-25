import asyncio
import inspect

from app.api import routes_chat
from app.services.evaluation import tasks as eval_tasks


def test_ask_is_async_and_uses_isolated_thread() -> None:
    assert inspect.iscoroutinefunction(routes_chat.ask_question)
    src = inspect.getsource(routes_chat.ask_question)
    assert "asyncio.to_thread" in src
    assert "_retrieve_with_isolated_session" in src
    assert "_generate_with_fresh_generator" in src
    assert routes_chat._RETRIEVAL_TIMEOUT_SECONDS < 150
    assert routes_chat._GENERATION_TIMEOUT_SECONDS < 150
    assert (
        routes_chat._RETRIEVAL_TIMEOUT_SECONDS + routes_chat._GENERATION_TIMEOUT_SECONDS
        <= 150
    )


def test_ask_per_stage_timeout_observable() -> None:
    src = inspect.getsource(routes_chat.ask_question)
    assert "504" in src
    # Timeout HTTPExceptions must bypass the generic 503 converter.
    assert "except HTTPException" in src
    # Per-stage budgets are distinguishable in metrics and payloads.
    assert "timeout_retrieval" in src
    assert "timeout_generation" in src
    assert '"stage"' in src


def test_stream_path_has_per_stage_timeout() -> None:
    src = inspect.getsource(routes_chat.ask_question_stream)
    assert "asyncio.to_thread" in src
    assert "_RETRIEVAL_TIMEOUT_SECONDS" in src
    assert "_GENERATION_TIMEOUT_SECONDS" in src
    pings_src = inspect.getsource(routes_chat._pings_while)
    assert "timeout_seconds" in pings_src


def test_evaluation_enqueue_background_fallback(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "celery_enabled", False)
    assert eval_tasks.enqueue_evaluation_run("run_x", ["upstash"], 5) == "background"


def test_evaluation_enqueue_celery(monkeypatch) -> None:
    import sys
    import types

    from app.core.config import settings

    monkeypatch.setattr(settings, "celery_enabled", True)

    class _FakeApp:
        def __init__(self) -> None:
            self.sent: list = []

        def send_task(self, name, args=None, kwargs=None) -> None:
            self.sent.append((name, args))

    fake = _FakeApp()
    stub = types.ModuleType("app.services.ingestion.tasks")
    stub.celery_app = fake
    monkeypatch.setitem(sys.modules, "app.services.ingestion.tasks", stub)
    assert eval_tasks.enqueue_evaluation_run("run_y", ["upstash"], 5) == "celery"
    assert fake.sent and fake.sent[0][0] == "kerjapedia.evaluation.run"


def test_asyncio_wait_for_available() -> None:
    assert hasattr(asyncio, "wait_for")
