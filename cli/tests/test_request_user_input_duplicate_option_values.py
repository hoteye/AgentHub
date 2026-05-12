from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    handle_request_user_input_command,
)
from cli.agent_cli.ui.request_user_input_state_runtime import (
    OTHER_OPTION_VALUE,
    PHASE_REVIEW,
    option_index_for_value,
    parse_request_user_input_spec,
    request_user_input_initial_state,
    response_payload,
    with_cursor_delta,
    with_move_previous,
    with_selected_current_option,
)


def _duplicate_option_values_payload() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "strategy",
                "header": "Strategy",
                "question": "Pick rollout strategy",
                "options": [
                    {"label": "Fast", "description": "Immediate rollout."},
                    {"label": "Fast", "description": "Immediate rollout with extra logging."},
                    {"label": "Safe", "description": "Phased rollout."},
                ],
            }
        ]
    }


def _duplicate_option_values_arg_text() -> str:
    return (
        '{"questions":['
        '{"id":"strategy","header":"Strategy","question":"Pick rollout strategy",'
        '"options":['
        '{"label":"Fast","description":"Immediate rollout."},'
        '{"label":"Fast","description":"Immediate rollout with extra logging."},'
        '{"label":"Safe","description":"Phased rollout."}'
        "]}"
        "]}"
    )


class RequestUserInputDuplicateOptionValuesTest(unittest.TestCase):
    def test_state_parser_allows_duplicate_values_and_selection_remains_deterministic(self) -> None:
        spec = parse_request_user_input_spec(_duplicate_option_values_payload())
        question = spec.questions[0]

        self.assertEqual(
            [option.value for option in question.options],
            ["Fast", "Fast", "Safe", OTHER_OPTION_VALUE],
        )

        state = request_user_input_initial_state(spec)
        state = with_cursor_delta(state, 1)
        state = with_selected_current_option(state)
        self.assertEqual(state.phase, PHASE_REVIEW)
        self.assertEqual(
            response_payload(state),
            {"answers": {"strategy": {"answers": ["Fast"]}}},
        )

        back_to_questions = with_move_previous(state)
        self.assertEqual(back_to_questions.cursor_index, 0)
        self.assertEqual(option_index_for_value(question, "Fast"), 0)

    def test_command_path_with_ambiguous_value_returns_stable_shape_and_followup_still_works(self) -> None:
        calls = {"count": 0}

        def _handler(_payload):
            calls["count"] += 1
            if calls["count"] == 1:
                return {"answers": {"strategy": "Fast"}}
            return {"answers": {"strategy": "Safe"}}

        runtime = SimpleNamespace(
            collaboration_mode="default",
            default_mode_request_user_input=True,
            request_user_input_handler=_handler,
        )

        first = handle_request_user_input_command(runtime, arg_text=_duplicate_option_values_arg_text())
        self.assertTrue(first.tool_events[0].ok)
        first_response = json.loads(first.assistant_text)
        self.assertEqual(first_response["answers"]["strategy"]["answers"], ["Fast"])
        self.assertEqual(
            first.tool_events[0].payload["response"]["answers"]["strategy"]["answers"],
            ["Fast"],
        )

        second = handle_request_user_input_command(runtime, arg_text=_duplicate_option_values_arg_text())
        self.assertTrue(second.tool_events[0].ok)
        second_response = json.loads(second.assistant_text)
        self.assertEqual(second_response["answers"]["strategy"]["answers"], ["Safe"])
