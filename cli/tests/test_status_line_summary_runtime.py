from __future__ import annotations

import unittest
from pathlib import Path

from cli.agent_cli.ui.status_line_summary_runtime import (
    build_provider_summary_text,
    build_status_summary_text,
    summary_segments,
)


class StatusLineSummaryRuntimeTest(unittest.TestCase):
    def test_summary_segments_prefer_provider_model_and_thread_name(self) -> None:
        segments = summary_segments(
            status_data={
                "provider_name": "openai",
                "provider_model": "gpt-5.4",
                "provider_reasoning_effort": "high",
                "thread_name": "resume flow",
                "thread_id": "thread_should_not_show",
            },
            cwd="/tmp/worktrees/agenthub",
        )

        self.assertEqual(segments, ["gpt-5.4", "resume flow", "agenthub"])

    def test_summary_segments_fall_back_to_provider_name_and_thread_id(self) -> None:
        segments = summary_segments(
            status_data={
                "provider_name": "openai",
                "provider_model": "-",
                "thread_name": " ",
                "thread_id": "27a33bd1fe264ee0aedb17dec9dca7d2",
            },
            cwd=None,
        )

        self.assertEqual(segments, ["openai", "27a33bd1fe26"])

    def test_build_status_summary_text_ignores_blank_values(self) -> None:
        text = build_status_summary_text(
            status_data={
                "provider_name": " ",
                "provider_model": " ",
                "thread_name": "",
                "thread_id": "-",
                "cwd": "/home/lyc/project/AgentHub/cli",
            }
        )

        self.assertEqual(text, "cli")

    def test_build_status_summary_text_skips_provider_when_not_ready(self) -> None:
        text = build_status_summary_text(
            status_data={
                "provider_ready": "false",
                "provider_name": "fallback",
                "provider_model": "gpt-5.4",
                "provider_reasoning_effort": "high",
                "thread_name": "resume flow",
            },
            cwd="/tmp/demo",
        )

        self.assertEqual(text, "resume flow · demo")

    def test_build_status_summary_text_supports_custom_separator(self) -> None:
        text = build_status_summary_text(
            status_data={
                "provider_model": "gpt-5.4",
                "thread_name": "session restore",
            },
            cwd="/tmp/demo",
            separator=" | ",
        )

        self.assertEqual(text, "gpt-5.4 | session restore | demo")

    def test_summary_segments_append_thread_id_when_name_missing_but_workspace_exists(self) -> None:
        segments = summary_segments(
            status_data={
                "provider_model": "gpt-5.4",
                "thread_name": "",
                "thread_id": "27a33bd1fe264ee0aedb17dec9dca7d2",
            },
            cwd="/tmp/demo",
        )

        self.assertEqual(segments, ["gpt-5.4", "demo", "27a33bd1fe26"])

    def test_summary_segments_omit_fallback_provider_name_when_model_missing(self) -> None:
        segments = summary_segments(
            status_data={
                "provider_ready": "true",
                "provider_name": "fallback",
                "provider_model": "-",
                "thread_name": "resume flow",
            },
            cwd="/tmp/demo",
        )

        self.assertEqual(segments, ["resume flow", "demo"])

    def test_build_status_summary_text_uses_status_data_cwd_when_explicit_cwd_absent(self) -> None:
        text = build_status_summary_text(
            status_data={
                "provider_model": "gpt-5.4",
                "cwd": "/home/lyc/project/AgentHub/cli",
            }
        )

        self.assertEqual(text, "gpt-5.4 · cli")

    def test_build_provider_summary_text_includes_provider_model_and_effort(self) -> None:
        text = build_provider_summary_text(
            status_data={
                "provider_ready": "true",
                "provider_name": "openai",
                "provider_model": "gpt-5.4",
                "provider_reasoning_effort": "high",
            }
        )

        self.assertEqual(text, "openai · gpt-5.4 · high")

    def test_build_provider_summary_text_includes_cwd_when_available(self) -> None:
        cwd = str(Path.home() / "project" / "AgentHub")
        text = build_provider_summary_text(
            status_data={
                "provider_ready": "true",
                "provider_name": "openai",
                "provider_model": "gpt-5.4",
                "provider_reasoning_effort": "high",
            },
            cwd=cwd,
        )

        self.assertEqual(text, "openai · gpt-5.4 · high · ~/project/AgentHub")

    def test_build_provider_summary_text_keeps_cwd_when_provider_not_ready(self) -> None:
        text = build_provider_summary_text(
            status_data={
                "provider_ready": "false",
                "provider_name": "openai",
                "provider_model": "gpt-5.4",
            },
            cwd="/tmp/workspace",
        )

        self.assertEqual(text, "/tmp/workspace")

    def test_build_provider_summary_text_omits_fallback_and_not_ready_provider(self) -> None:
        self.assertEqual(
            build_provider_summary_text(
                status_data={
                    "provider_ready": "false",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                }
            ),
            "",
        )
        self.assertEqual(
            build_provider_summary_text(
                status_data={
                    "provider_ready": "true",
                    "provider_name": "fallback",
                    "provider_model": "-",
                    "provider_reasoning_effort": "-",
                }
            ),
            "",
        )
