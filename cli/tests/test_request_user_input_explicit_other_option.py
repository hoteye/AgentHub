from __future__ import annotations

import unittest

from cli.agent_cli.ui.request_user_input_state_runtime import (
    parse_request_user_input_spec,
)


def _payload_with_explicit_other_option() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "confirm_path",
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {"label": "Yes", "description": "Continue."},
                    {
                        "label": "Other",
                        "description": "Custom answer from caller.",
                        "is_other": True,
                    },
                ],
            }
        ]
    }


class RequestUserInputExplicitOtherOptionTest(unittest.TestCase):
    def test_parse_spec_rejects_explicit_other_label_from_caller(self) -> None:
        with self.assertRaisesRegex(ValueError, "reserved option label"):
            parse_request_user_input_spec(_payload_with_explicit_other_option())
