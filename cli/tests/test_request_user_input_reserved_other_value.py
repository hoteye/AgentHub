from __future__ import annotations

import unittest

from cli.agent_cli.ui.request_user_input_state_runtime import (
    OTHER_OPTION_VALUE,
    parse_request_user_input_spec,
)


def _payload_with_reserved_value_field() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "confirm_path",
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {
                        "label": "Caller custom",
                        "description": "Caller-supplied option value.",
                        "value": OTHER_OPTION_VALUE,
                    },
                    {"label": "Yes", "description": "Continue."},
                ],
            }
        ]
    }


def _payload_with_reserved_label() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "confirm_path",
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {
                        "label": OTHER_OPTION_VALUE,
                        "description": "Caller-provided reserved label.",
                    },
                    {"label": "No", "description": "Stop."},
                ],
            }
        ]
    }


class RequestUserInputReservedOtherValueTest(unittest.TestCase):
    def test_parse_spec_ignores_upstream_value_field_and_keeps_single_internal_other(self) -> None:
        spec = parse_request_user_input_spec(_payload_with_reserved_value_field())
        question = spec.questions[0]

        self.assertEqual([option.value for option in question.options], ["Caller custom", "Yes", OTHER_OPTION_VALUE])
        self.assertTrue(question.options[-1].is_other)
        self.assertEqual(
            sum(1 for option in question.options if option.value == OTHER_OPTION_VALUE),
            1,
        )

    def test_parse_spec_rejects_reserved_other_label_from_caller(self) -> None:
        with self.assertRaisesRegex(ValueError, "reserved option label"):
            parse_request_user_input_spec(_payload_with_reserved_label())
