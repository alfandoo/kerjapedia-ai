from app.services.answering.conversation_summary import append_summary, summary_context
from app.services.answering.memory_hardening import build_memory_context


def citation(document="pp35", article="Pasal 4"):
    return {"document_id": document, "short_title": "PP 35/2021", "article": article}


def test_summary_keeps_bounded_cited_turns_and_redacts_personal_data():
    summary = {}
    for index in range(12):
        summary = append_summary(
            summary,
            f"Bagaimana aturan PKWT ke-{index} untuk 081234567890?",
            f"msg_{index}",
            [citation()],
        )
    assert len(summary["turns"]) == 8
    assert summary["turns"][-1]["source_message_id"] == "msg_11"
    assert "081234567890" not in str(summary)
    assert summary["turns"][-1]["document_ids"] == ["pp35"]


def test_summary_resolves_long_followup_without_old_answer_text():
    summary = append_summary({}, "Bagaimana aturan PKWT?", "msg_1", [citation()])
    for index in range(5):
        summary = append_summary(
            summary, f"Bagaimana masa PKWT {index}?", f"msg_{index + 2}", [citation()]
        )
    context = summary_context("Bagaimana ketentuannya?", summary)
    assert context is not None
    assert context["document_ids"] == ("pp35",)
    assert "PP 35/2021" in context["text"]


def test_summary_does_not_infer_ambiguous_yang_tadi_across_topics():
    summary = append_summary({}, "Bagaimana aturan PKWT?", "msg_1", [citation()])
    summary = append_summary(
        summary,
        "Bagaimana aturan THR?",
        "msg_2",
        [{"document_id": "permen6", "short_title": "Permen 6/2016", "article": "Pasal 2"}],
    )
    assert summary_context("Bagaimana yang tadi?", summary) is None
    assert summary_context("Bagaimana yang itu?", summary) is None
    assert summary_context("What about the THR rule?", summary) is None


def test_summary_resolves_bilingual_followup_after_recent_window():
    summary = append_summary({}, "Bagaimana aturan PKWT?", "msg_1", [citation()])
    memory = build_memory_context("How about that rule?", [], summary=summary)
    assert memory.used is True
    assert memory.context_document_ids == ("pp35",)
    assert memory.question_language == "en"


def test_ambiguous_reference_does_not_use_recent_topic():
    summary = append_summary({}, "Bagaimana aturan PKWT?", "msg_1", [citation()])
    summary = append_summary(
        summary,
        "Bagaimana aturan THR?",
        "msg_2",
        [{"document_id": "thr", "short_title": "Permen THR", "article": "Pasal 2"}],
    )
    memory = build_memory_context("Bagaimana yang tadi?", [], summary=summary)
    assert memory.used is False
