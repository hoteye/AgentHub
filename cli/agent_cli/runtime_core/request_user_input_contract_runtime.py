from __future__ import annotations

from typing import Any


_RESERVED_OTHER_OPTION_LABELS = {"other", "__other__"}


def normalize_request_user_input_questions(questions: Any) -> list[dict[str, Any]]:
    if not isinstance(questions, list):
        raise ValueError("failed to parse function arguments: expected questions to be an array")
    normalized_questions: list[dict[str, Any]] = []
    seen_question_ids: set[str] = set()
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError("failed to parse function arguments: expected question entries to be objects")
        question_id = str(item.get("id") or "").strip()
        header = str(item.get("header") or "").strip()
        question_text = str(item.get("question") or "").strip()
        options = item.get("options")
        if not question_id or not header or not question_text or not isinstance(options, list):
            raise ValueError("failed to parse function arguments: invalid question payload")
        if question_id in seen_question_ids:
            raise ValueError("failed to parse function arguments: duplicate question id")
        seen_question_ids.add(question_id)
        normalized_options: list[dict[str, str]] = []
        for option in options:
            if not isinstance(option, dict):
                raise ValueError("failed to parse function arguments: invalid option payload")
            label = str(option.get("label") or "").strip()
            description = str(option.get("description") or "").strip()
            if not label or not description:
                raise ValueError("request_user_input requires non-empty options for every question")
            if label.lower() in _RESERVED_OTHER_OPTION_LABELS:
                raise ValueError("failed to parse function arguments: reserved option label")
            normalized_options.append({"label": label, "description": description})
        if not normalized_options:
            raise ValueError("request_user_input requires non-empty options for every question")
        normalized_questions.append(
            {
                "id": question_id,
                "header": header,
                "question": question_text,
                "options": normalized_options,
                "is_other": True,
            }
        )
    return normalized_questions


def normalize_request_user_input_response(
    response: dict[str, Any],
    *,
    question_ids: set[str],
) -> dict[str, Any]:
    normalized = dict(response or {})
    raw_answers = normalized.get("answers")
    if not isinstance(raw_answers, dict):
        normalized["answers"] = {}
        return normalized
    normalized_answers: dict[str, dict[str, list[str]]] = {}
    for raw_key, raw_value in raw_answers.items():
        answer_key = str(raw_key or "").strip()
        if not answer_key:
            continue
        if question_ids and answer_key not in question_ids:
            continue
        normalized_values: list[str] = []
        if isinstance(raw_value, dict):
            candidate_values = raw_value.get("answers")
            if not isinstance(candidate_values, list):
                single_value = raw_value.get("answer")
                candidate_values = [single_value] if single_value is not None else []
            normalized_values = [str(item).strip() for item in candidate_values if str(item).strip()]
        elif isinstance(raw_value, list):
            normalized_values = [str(item).strip() for item in raw_value if str(item).strip()]
        else:
            value = str(raw_value or "").strip()
            normalized_values = [value] if value else []
        normalized_answers[answer_key] = {"answers": normalized_values}
    normalized["answers"] = normalized_answers
    return normalized
