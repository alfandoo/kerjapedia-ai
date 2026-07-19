from __future__ import annotations

import json
from pathlib import Path

from app.services.evaluation.schemas import EvaluationQuestion


def load_evaluation_dataset(path: Path) -> tuple[dict, list[EvaluationQuestion]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    questions = [EvaluationQuestion.from_dict(item) for item in payload["questions"]]
    declared_count = payload.get("question_count", len(questions))
    if declared_count != len(questions):
        raise ValueError(
            f"Evaluation dataset declares {declared_count} questions but contains {len(questions)}."
        )
    question_ids = [question.question_id for question in questions]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("Evaluation question IDs must be unique.")
    return payload, questions
