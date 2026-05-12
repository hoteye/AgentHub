from __future__ import annotations

import unittest

from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.ui.transcript_controller import TranscriptControllerMixin


class _TranscriptProbe(TranscriptControllerMixin):
    def __init__(self) -> None:
        self.notices: list[str] = []

    def _write_system_notice(self, content: str) -> None:  # type: ignore[override]
        self.notices.append(str(content))


class RequestUserInputTranscriptProjectionTest(unittest.TestCase):
    def test_request_user_input_summary_renders_canonical_answers(self) -> None:
        probe = _TranscriptProbe()
        response = PromptResponse(
            user_text="trigger",
            assistant_text="done",
            tool_events=[
                ToolEvent(
                    name="request_user_input",
                    ok=True,
                    summary="request_user_input completed",
                    payload={
                        "response": {
                            "answers": {
                                "confirm_path": {"answers": ["Yes (Recommended)"]},
                                "scope": {"answers": ["src", "tests"]},
                            },
                            "metadata": {"source": "local_tui"},
                        }
                    },
                )
            ],
        )

        probe._write_request_user_input_summary(response)

        self.assertEqual(
            probe.notices,
            [
                "User input confirm_path -> Yes (Recommended)",
                "User input scope -> src, tests",
            ],
        )

    def test_request_user_input_summary_renders_cancelled_notice_for_missing_response(self) -> None:
        probe = _TranscriptProbe()
        response = PromptResponse(
            user_text="trigger",
            assistant_text="done",
            tool_events=[
                ToolEvent(
                    name="request_user_input",
                    ok=False,
                    summary="request_user_input cancelled",
                    payload={},
                )
            ],
        )

        probe._write_request_user_input_summary(response)

        self.assertEqual(probe.notices, ["User input request was cancelled."])

    def test_request_user_input_summary_renders_cancelled_notice_for_empty_answers(self) -> None:
        probe = _TranscriptProbe()
        response = PromptResponse(
            user_text="trigger",
            assistant_text="done",
            tool_events=[
                ToolEvent(
                    name="request_user_input",
                    ok=True,
                    summary="request_user_input completed",
                    payload={"response": {"answers": {}}},
                )
            ],
        )

        probe._write_request_user_input_summary(response)

        self.assertEqual(probe.notices, ["User input request was cancelled."])

    def test_request_user_input_summary_ignores_non_request_events(self) -> None:
        probe = _TranscriptProbe()
        response = PromptResponse(
            user_text="trigger",
            assistant_text="done",
            tool_events=[
                ToolEvent(
                    name="shell",
                    ok=True,
                    summary="shell done",
                    payload={"stdout": "ok"},
                )
            ],
        )

        probe._write_request_user_input_summary(response)

        self.assertEqual(probe.notices, [])

