from __future__ import annotations

import unittest

from cli.agent_cli.ui.request_user_input_state_runtime import (
    OTHER_OPTION_VALUE,
    PHASE_QUESTIONS,
    PHASE_REVIEW,
    all_questions_answered,
    first_unanswered_question_index,
    parse_request_user_input_spec,
    request_user_input_initial_state,
    response_payload,
    review_answer_rows,
    with_cursor_delta,
    with_move_next,
    with_return_to_unanswered,
    with_selected_current_option,
)


def _payload_two_questions() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "confirm_path",
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {"label": "Yes (Recommended)", "description": "Continue."},
                    {"label": "No", "description": "Stop."},
                ],
            },
            {
                "id": "delivery",
                "header": "Deliver",
                "question": "Deliverable?",
                "options": [
                    {"label": "Patch", "description": "Patch only."},
                    {"label": "Patch + notes", "description": "Patch and notes."},
                ],
            },
        ]
    }


class RequestUserInputStateRuntimeTest(unittest.TestCase):
    def test_parse_spec_adds_other_option_and_limit(self) -> None:
        spec = parse_request_user_input_spec(_payload_two_questions())
        self.assertEqual(len(spec.questions), 2)
        for question in spec.questions:
            self.assertEqual(question.options[-1].value, OTHER_OPTION_VALUE)
            self.assertTrue(question.options[-1].is_other)

        with self.assertRaisesRegex(ValueError, "at most 3 questions"):
            parse_request_user_input_spec(
                {
                    "questions": [
                        {
                            "id": f"q{index}",
                            "header": "H",
                            "question": "Q?",
                            "options": [
                                {"label": "A", "description": "d1"},
                                {"label": "B", "description": "d2"},
                            ],
                        }
                        for index in range(4)
                    ]
                }
            )

    def test_state_flow_single_select_and_other_text_to_review(self) -> None:
        spec = parse_request_user_input_spec(_payload_two_questions())
        state = request_user_input_initial_state(spec)
        self.assertEqual(state.phase, PHASE_QUESTIONS)

        state = with_selected_current_option(state)
        self.assertEqual(state.question_index, 1)
        self.assertEqual(state.phase, PHASE_QUESTIONS)

        state = with_cursor_delta(state, 2)
        state = with_selected_current_option(state)
        self.assertEqual(state.selected_option("delivery"), OTHER_OPTION_VALUE)
        self.assertFalse(all_questions_answered(state))

        state = state
        state = with_move_next(state)
        self.assertEqual(state.phase, PHASE_REVIEW)
        self.assertEqual(first_unanswered_question_index(state), 1)

    def test_return_to_unanswered_and_review_payload(self) -> None:
        spec = parse_request_user_input_spec(_payload_two_questions())
        state = request_user_input_initial_state(spec)
        state = with_selected_current_option(state)
        state = with_move_next(state)
        self.assertEqual(state.phase, PHASE_REVIEW)

        rows = review_answer_rows(state)
        self.assertEqual(rows[0][1], "Yes (Recommended)")
        self.assertEqual(rows[1][1], "<unanswered>")

        state = with_return_to_unanswered(state)
        self.assertEqual(state.phase, PHASE_QUESTIONS)
        self.assertEqual(state.question_index, 1)

        state = with_cursor_delta(state, 1)
        state = with_selected_current_option(state)
        state = with_move_next(state)
        self.assertTrue(all_questions_answered(state))
        self.assertEqual(state.phase, PHASE_REVIEW)

        payload = response_payload(state)
        self.assertEqual(
            payload,
            {
                "answers": {
                    "confirm_path": {"answers": ["Yes (Recommended)"]},
                    "delivery": {"answers": ["Patch + notes"]},
                }
            },
        )

