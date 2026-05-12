from __future__ import annotations

from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
    normalize_request_user_input_response,
)


def test_normalize_request_user_input_questions_adds_is_other_and_trims_fields() -> None:
    normalized = normalize_request_user_input_questions(
        [
            {
                "id": " confirm_path ",
                "header": " Confirm ",
                "question": " Proceed? ",
                "options": [
                    {"label": " Yes (Recommended) ", "description": " Continue. "},
                    {"label": " No ", "description": " Stop. "},
                ],
            }
        ]
    )

    assert normalized == [
        {
            "id": "confirm_path",
            "header": "Confirm",
            "question": "Proceed?",
            "options": [
                {"label": "Yes (Recommended)", "description": "Continue."},
                {"label": "No", "description": "Stop."},
            ],
            "is_other": True,
        }
    ]


def test_normalize_request_user_input_response_canonicalizes_answers_and_filters_unknown_keys() -> None:
    normalized = normalize_request_user_input_response(
        {
            "answers": {
                "confirm_path": "yes",
                "mode": ["fast", "safe", ""],
                "extra": {"answers": ["ignored"]},
                "shape_a": {"answer": "single"},
                "shape_b": {"answers": ["a", " ", "b"]},
            },
            "metadata": {"source": "test"},
        },
        question_ids={"confirm_path", "mode", "shape_a", "shape_b"},
    )

    assert normalized["answers"] == {
        "confirm_path": {"answers": ["yes"]},
        "mode": {"answers": ["fast", "safe"]},
        "shape_a": {"answers": ["single"]},
        "shape_b": {"answers": ["a", "b"]},
    }
    assert normalized["metadata"] == {"source": "test"}


def test_normalize_request_user_input_response_defaults_to_empty_answers_for_invalid_payload() -> None:
    assert normalize_request_user_input_response({}, question_ids={"confirm_path"}) == {"answers": {}}
    assert normalize_request_user_input_response({"answers": []}, question_ids={"confirm_path"}) == {"answers": {}}

