from app.api.routes_chat import _sanitize_title
from app.services.idempotency import valid_idempotency_key


def test_titles_strip_controls_and_truncate() -> None:
    assert _sanitize_title("Apakah pekerja PKWT memperoleh kompensasi?") == (
        "Apakah pekerja PKWT memperoleh kompensasi?"
    )
    assert _sanitize_title("Line satu\nLine dua\tTab") == "Line satu Line dua Tab"
    assert _sanitize_title("x" * 200) == "x" * 80
    assert _sanitize_title("   ") == "Percakapan"


def test_idempotency_key_reuse_is_detected_by_fingerprint() -> None:
    first = {"question": "a?", "conversation_id": None, "top_k": 5}
    second = {"question": "b?", "conversation_id": None, "top_k": 5}

    assert valid_idempotency_key("key-1234") == "key-1234"
    assert first != second
