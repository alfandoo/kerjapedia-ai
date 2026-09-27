from contextlib import contextmanager
from types import SimpleNamespace

from app.api import routes_chat


def test_request_observation_records_mode_latency_retry_and_provider_failure(monkeypatch):
    saved = []

    class Session:
        def add(self, row):
            saved.append(row)

        def commit(self):
            pass

    @contextmanager
    def fake_session():
        yield Session()

    monkeypatch.setattr(routes_chat, "create_session", fake_session)
    monkeypatch.setattr(routes_chat, "drain_stage_accumulator", lambda: [])
    answer = SimpleNamespace(
        debug={
            "token_usage": {"prompt_tokens": 40, "completion_tokens": 10},
            "transient_retries": 2,
            "provider_failure_type": "RateLimitError",
            "llm_model": "test-model",
        },
        claims=[],
    )
    routes_chat._record_request_observation(
        "answered", answer=answer, latency_ms=500,
        turn_id="msg_1", reasoning_mode="deep",
        first_status_ms=2, first_content_ms=490,
    )
    row = saved[0]
    assert row.turn_id == "msg_1"
    assert row.reasoning_mode == "deep"
    assert row.time_to_first_status_ms == 2
    assert row.time_to_first_content_ms == 490
    assert row.request_latency_ms == 500
    assert row.retry_count == 2
    assert row.provider_failure is True
    assert row.prompt_tokens == 40


def test_cancelled_observation_records_disconnect_and_actual_known_tokens(monkeypatch):
    saved = []

    class Session:
        def add(self, row):
            saved.append(row)

        def commit(self):
            pass

    @contextmanager
    def fake_session():
        yield Session()

    monkeypatch.setattr(routes_chat, "create_session", fake_session)
    monkeypatch.setattr(routes_chat, "drain_stage_accumulator", lambda: [])
    routes_chat._record_request_observation(
        "cancelled", latency_ms=50, turn_id="msg_2",
        reasoning_mode="fast", first_status_ms=1,
        disconnected=True,
        usage_override={"prompt_tokens": 9, "completion_tokens": 0},
    )
    row = saved[0]
    assert row.outcome == "cancelled"
    assert row.disconnected is True
    assert row.time_to_first_content_ms is None
    assert row.prompt_tokens == 9
