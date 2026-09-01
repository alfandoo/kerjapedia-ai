from __future__ import annotations

RELEASE_QUALITY_GATES = {
    "recall_at_5": 0.90,
    "recall_at_10": 0.95,
    "citation_precision": 0.95,
    "refusal_recall": 0.95,
    "refusal_precision": 0.90,
    "language_accuracy": 0.99,
}

REQUIRED_RELEASE_SCENARIOS = frozenset(
    {
        "follow_up",
        "typo",
        "bilingual",
        "topic_switch",
        "historical",
        "complex",
        "hard_negative",
        "prompt_injection",
    }
)
